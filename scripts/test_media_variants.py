import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from media_variants import _inside, image_variants


class MediaVariantsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.output = self.root / 'output'
        self.cache = self.root / 'cache'

    def create(self, name, size=(1000, 500), mode='RGB', colour='white'):
        source = self.root / name
        Image.new(mode, size, colour).save(source)
        return source

    def variants(self, source):
        return image_variants(source, self.output, self.cache)

    def test_no_upscale_and_natural_width_and_source_unchanged(self):
        source = self.create('original.png')
        original = source.read_bytes()
        records = self.variants(source)
        self.assertEqual([r['width'] for r in records], [480, 960, 1000])
        for record in records:
            path = self.output / record['file']
            with Image.open(path) as derived:
                self.assertEqual(derived.size, (record['width'], record['height']))
                self.assertLessEqual(derived.width, 1000)
            self.assertEqual(path.stat().st_size, record['bytes'])
        self.assertEqual(source.read_bytes(), original)
        tiny = self.create('tiny.jpg', (100, 50))
        self.assertEqual([r['width'] for r in self.variants(tiny)], [100])
        large = self.create('large.png', (1800, 500))
        self.assertEqual([r['width'] for r in self.variants(large)], [480, 960, 1440])

    def test_transparency_retained(self):
        source = self.create('alpha.png', (500, 250), 'RGBA', (255, 0, 0, 0))
        with Image.open(source) as image:
            image.putpixel((250, 125), (0, 0, 0, 255))
            image.save(source)
        record = self.variants(source)[-1]
        with Image.open(self.output / record['file']) as derived:
            self.assertIn('A', derived.getbands())
            self.assertEqual(derived.getpixel((0, 0))[3], 0)
            self.assertEqual(derived.getpixel((250, 125))[3], 255)

    def test_cache_reuse_and_deleted_output_restored_without_encoding(self):
        source = self.create('original.png')
        first = self.variants(source)
        files = {r['file']: (self.output / r['file']).read_bytes() for r in first}
        mtimes = {p: p.stat().st_mtime_ns for p in self.cache.iterdir()}
        for record in first:
            (self.output / record['file']).unlink()
        with patch.object(Image.Image, 'save', side_effect=AssertionError('re-encoded cache')):
            self.assertEqual(self.variants(source), first)
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.cache.iterdir()}, mtimes)
        for name, expected in files.items():
            self.assertEqual((self.output / name).read_bytes(), expected)

    def test_animated_gif_and_webp_are_not_flattened(self):
        for extension in ('gif', 'webp'):
            with self.subTest(extension=extension):
                source = self.root / f'animated.{extension}'
                first = Image.new('RGB', (32, 32), 'red')
                second = Image.new('RGB', (32, 32), 'blue')
                first.save(source, save_all=True, append_images=[second], duration=100, loop=0)
                original = source.read_bytes()
                self.assertEqual(self.variants(source), [])
                self.assertEqual(source.read_bytes(), original)
                self.assertFalse(self.output.exists())

    def test_exif_orientation_applied_to_visual_dimensions(self):
        source = self.root / 'rotated.jpg'
        image = Image.new('RGB', (600, 1000), 'white')
        exif = Image.Exif()
        exif[274] = 6
        image.save(source, exif=exif)
        before = source.read_bytes()
        record = self.variants(source)[-1]
        self.assertEqual((record['width'], record['height']), (1000, 600))
        with Image.open(self.output / record['file']) as derived:
            self.assertEqual(derived.size, (1000, 600))
            self.assertNotIn(274, derived.getexif())
        self.assertEqual(source.read_bytes(), before)

    def test_corrupt_cache_is_repaired_and_source_change_invalidates_cache(self):
        source = self.create('original.png')
        first = self.variants(source)
        name = Path(first[0]['file']).name
        (self.cache / name).write_bytes(b'broken')
        self.assertEqual(self.variants(source), first)
        self.assertEqual((self.cache / name).read_bytes(),
                         (self.output / first[0]['file']).read_bytes())
        Image.new('RGB', (1000, 500), 'blue').save(source)
        second = self.variants(source)
        self.assertNotEqual(first[0]['file'], second[0]['file'])

    def test_untrusted_manifest_paths_never_used(self):
        source = self.create('original.png')
        first = self.variants(source)
        manifest_path = next(self.cache.glob('*.json'))
        manifest = json.loads(manifest_path.read_text())
        manifest['variants'][0]['file'] = '../../outside.webp'
        manifest_path.write_text(json.dumps(manifest))
        self.assertEqual(self.variants(source), first)
        self.assertFalse((self.root / 'outside.webp').exists())

    def test_invalid_cache_manifest_is_rebuilt(self):
        source = self.create('original.png', (100, 50))
        first = self.variants(source)
        manifest_path = next(self.cache.glob('*.json'))
        for malformed in ('invalid JSON',
                          json.dumps({'key': json.loads(manifest_path.read_text())['key'],
                                      'variants': None})):
            manifest_path.write_text(malformed)
            self.assertEqual(self.variants(source), first)

    def test_path_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            _inside(self.output, '../../outside.webp')

    def test_static_gif_and_webp_supported(self):
        for extension in ('gif', 'webp'):
            with self.subTest(extension=extension):
                source = self.create(f'static.{extension}', (100, 50))
                original = source.read_bytes()
                self.assertEqual([r['width'] for r in self.variants(source)], [100])
                self.assertEqual(source.read_bytes(), original)

    def test_destination_symlink_cannot_escape_output(self):
        source = self.create('original.png')
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        self.output.mkdir()
        try:
            (self.output / 'assets').symlink_to(elsewhere, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation unavailable on this Windows account')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.variants(source)
        self.assertFalse(list(elsewhere.rglob('*.webp')))

    def test_invalid_and_unsupported_files_keep_original_fallback(self):
        invalid = self.root / 'invalid.png'
        invalid.write_bytes(b'not an image')
        self.assertEqual(self.variants(invalid), [])
        unsupported = self.create('unsupported.bmp')
        self.assertEqual(self.variants(unsupported), [])


if __name__ == '__main__':
    unittest.main()
