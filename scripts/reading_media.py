"""Progressive image presentation, without changing the source artwork."""
from __future__ import annotations

import html
import re
import struct
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


@lru_cache(maxsize=None)
def image_size(path: Path) -> tuple[int, int] | None:
    """Read PNG/JPEG/GIF dimensions using the standard library only."""
    with path.open('rb') as stream:
        header = stream.read(24)
        if header.startswith(b'\x89PNG\r\n\x1a\n') and len(header) == 24:
            return struct.unpack('>II', header[16:24])
        if header[:6] in (b'GIF87a', b'GIF89a'):
            return struct.unpack('<HH', header[6:10])
        if not header.startswith(b'\xff\xd8'):
            return None
        stream.seek(2)
        while True:
            byte = stream.read(1)
            if not byte:
                return None
            if byte != b'\xff':
                continue
            marker = stream.read(1)
            while marker == b'\xff':
                marker = stream.read(1)
            if not marker or marker in (b'\xda', b'\xd9'):
                return None
            if marker == b'\x00' or marker[0] in range(0xD0, 0xD9):
                continue
            length_bytes = stream.read(2)
            if len(length_bytes) != 2:
                return None
            length = struct.unpack('>H', length_bytes)[0]
            if length < 2:
                return None
            if marker[0] in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                             0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                data = stream.read(5)
                if len(data) < 5:
                    return None
                height, width = struct.unpack('>HH', data[1:5])
                return width, height
            stream.seek(length - 2, 1)


class ImageTag(HTMLParser):
    def handle_starttag(self, tag, attrs):
        self.attrs = dict(attrs)


def enhance_images(rendered: str, output: Path, prefix: str) -> str:
    def replace(match, pending=None):
        parser = ImageTag()
        parser.feed(match.group())
        attrs = parser.attrs
        src = attrs.get('src', '')
        parsed = urlsplit(src)
        if not parsed.netloc and not parsed.scheme and parsed.path.startswith(prefix):
            path = (output / unquote(parsed.path.removeprefix(prefix))).resolve()
            if path.is_relative_to(output.resolve()) and path.is_file():
                size = image_size(path)
                if size:
                    attrs['width'], attrs['height'] = map(str, size)
        attrs.update(loading='lazy', decoding='async')
        image = '<img ' + ' '.join(f'{k}="{html.escape(v or "", quote=True)}"'
                                 for k, v in attrs.items()) + '>'
        # The image and its original alt remain readable without JavaScript.
        # JavaScript exposes a separate, labelled enlargement control.
        caption = attrs.get('alt', 'Article illustration')
        button = ('<button type="button" class="image-zoom" hidden data-image="'
                  + html.escape(src, quote=True) + '" data-alt="'
                  + html.escape(caption, quote=True) + '" data-caption="'
                  + html.escape(caption, quote=True)
                  + '" aria-haspopup="dialog">Enlarge image'
                  + '<span class="sr-only">: ' + html.escape(caption)
                  + '</span></button>')
        if pending is not None:
            pending.append(button)
            return image
        return image + button

    def replace_link_or_image(match):
        # Markdown often wraps an image in a link to its original. Keep that
        # destination intact and put controls AFTER it, never inside the link.
        if match.group().startswith('<a'):
            pending = []
            anchor = re.sub(r'<img\b[^>]*>', lambda img: replace(img, pending), match.group())
            return anchor + ''.join(pending)
        return replace(match)

    return re.sub(r'<a\b[^>]*>(?:(?!</?a\b).)*?</a>|<img\b[^>]*>',
                  replace_link_or_image, rendered, flags=re.S)


IMAGE_VIEWER = '''<dialog id="image-viewer" aria-label="Enlarged illustration">
<div class="viewer-tools"><p>Original illustration · scroll to explore</p><div class="viewer-buttons"><button id="viewer-size-toggle" class="button" type="button" aria-controls="viewer-image">Original size</button><button id="viewer-close" class="button" type="button">Close image</button></div></div>
<div class="viewer-scroll" tabindex="0" role="region" aria-label="Original size image; scroll to explore"><img id="viewer-image" alt="Enlarged article illustration"></div>
<p id="viewer-caption"></p></dialog>'''
