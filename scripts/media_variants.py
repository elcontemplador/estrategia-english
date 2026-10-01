"""Reproducible responsive WebP copies; original artwork is never changed."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile


WIDTHS = (480, 960, 1440)
QUALITY = 86
METHOD = 6
VERSION = 1
SUPPORTED = {'PNG', 'JPEG', 'GIF', 'WEBP'}


def _write(path: Path, data: bytes) -> None:
    """Atomically replace a generated file inside its already checked directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Generated media path escapes its destination')
    return path


def image_variants(source: Path, output: Path, cache: Path) -> list[dict]:
    """Return file/width/height/bytes records relative to ``output``.

    Every derived image has at most the original's visual width. Small originals
    keep their natural width; large ones get 480/960/1440-pixel candidates. The
    cache key includes the source bytes and encoding configuration. Animation is
    deliberately left on the original image instead of flattened into a still.
    Pillow absence or undecodable artwork leaves the original-image fallback.
    """
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError, __version__
    except ImportError:
        return []
    source, output, cache = Path(source).resolve(), Path(output).resolve(), Path(cache).resolve()
    source_data = source.read_bytes()
    config = {'version': VERSION, 'widths': WIDTHS, 'quality': QUALITY,
              'method': METHOD, 'pillow': __version__, 'exact': True}
    config_bytes = json.dumps(config, sort_keys=True, separators=(',', ':')).encode()
    key = hashlib.sha256(source_data + b'\0' + config_bytes).hexdigest()
    # These names are computed, never taken from a cache manifest or source name.
    manifest_path = _inside(cache, f'{key}.json')
    try:
        with Image.open(io.BytesIO(source_data)) as original:
            if original.format not in SUPPORTED or getattr(original, 'n_frames', 1) > 1:
                return []
            oriented = ImageOps.exif_transpose(original)
            oriented.load()
            has_alpha = 'A' in oriented.getbands() or 'transparency' in oriented.info
            image = oriented.convert('RGBA' if has_alpha else 'RGB')
            icc_profile = oriented.info.get('icc_profile')
    except (UnidentifiedImageError, OSError, ValueError):
        return []
    natural_width, natural_height = image.size
    widths = sorted({width for width in WIDTHS if width <= natural_width}
                    | ({natural_width} if natural_width <= WIDTHS[-1] else set()))
    records = [{'file': f'assets/optimized/images/{key}-w{width}.webp',
                'width': width, 'height': max(1, round(natural_height * width / natural_width))}
               for width in widths]
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        manifest = None
    cached = {}
    # Validate only the generated names; untrusted manifest paths are never used.
    if (isinstance(manifest, dict) and manifest.get('key') == key
            and isinstance(manifest.get('variants'), list)):
        for record in manifest['variants']:
            if isinstance(record, dict) and isinstance(record.get('file'), str):
                cached[record['file']] = record
    final = []
    manifest_records = []
    for record in records:
        name = Path(record['file']).name
        cached_path = _inside(cache, name)
        target = _inside(output, record['file'])
        if source in (cached_path, target, manifest_path):
            raise ValueError('Generated media would overwrite its source')
        data = None
        previous = cached.get(record['file'], {})
        if (previous.get('width') == record['width']
                and previous.get('height') == record['height'] and cached_path.is_file()):
            candidate = cached_path.read_bytes()
            if (len(candidate) == previous.get('bytes')
                    and hashlib.sha256(candidate).hexdigest() == previous.get('sha256')):
                data = candidate
        if data is None:
            resized = image if image.size == (record['width'], record['height']) else image.resize(
                (record['width'], record['height']), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            options = {'format': 'WEBP', 'quality': QUALITY, 'method': METHOD, 'exact': True}
            if icc_profile:
                options['icc_profile'] = icc_profile
            resized.save(stream, **options)
            data = stream.getvalue()
            _write(cached_path, data)
        if not target.is_file() or target.read_bytes() != data:
            _write(target, data)
        public = dict(record, bytes=len(data))
        final.append(public)
        manifest_records.append(dict(public, sha256=hashlib.sha256(data).hexdigest()))
    manifest_data = (json.dumps({'key': key, 'config': config, 'variants': manifest_records},
                                indent=2, sort_keys=True) + '\n').encode('utf-8')
    if not manifest_path.is_file() or manifest_path.read_bytes() != manifest_data:
        _write(manifest_path, manifest_data)
    return final
