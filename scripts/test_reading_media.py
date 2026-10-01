import struct
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from reading_media import enhance_images, image_size


class InteractiveParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside_link = False
        self.nested = []
        self.images = []
        self.buttons = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a': self.inside_link = True
        if tag == 'button':
            self.buttons.append(dict(attrs))
            if self.inside_link: self.nested.append(tag)
        if tag == 'img': self.images.append(dict(attrs))
    def handle_endtag(self, tag):
        if tag == 'a': self.inside_link = False


class ReadingMediaTests(unittest.TestCase):
    def test_dimensions_and_linked_images_have_separate_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = output/'assets/images/test.png'
            path.parent.mkdir(parents=True)
            header = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' + struct.pack('>II', 800, 600)
            path.write_bytes(header)
            self.assertEqual(image_size(path), (800, 600))
            source = ('<p><a href="https://example.test/reference">A reference</a></p>'
                      '<p><a href="https://example.test/image"><img alt="A &amp; B" src="/edition/assets/images/test.png"></a></p>'
                      '<p><img alt="Second image" src="/edition/assets/images/test.png"></p>')
            rendered = enhance_images(source, output, '/edition/')
            parsed = InteractiveParser(); parsed.feed(rendered)
            self.assertFalse(parsed.nested)
            self.assertEqual(len(parsed.images), 2)
            self.assertEqual(len(parsed.buttons), 2)
            self.assertTrue(all(img['width']=='800' and img['height']=='600' for img in parsed.images))
            self.assertTrue(all(img['loading']=='lazy' for img in parsed.images))
            self.assertIn('<a href="https://example.test/reference">A reference</a>', rendered)
            self.assertIn('href="https://example.test/image"', rendered)
            self.assertEqual(parsed.buttons[0]['data-alt'], 'A & B')
            self.assertEqual(path.read_bytes(), header)

    def test_remote_images_keep_source_without_fetching(self):
        with tempfile.TemporaryDirectory() as directory:
            rendered = enhance_images('<img alt="Remote image" src="https://example.test/a.png">', Path(directory), '/edition/')
            self.assertIn('src="https://example.test/a.png"', rendered)
            self.assertNotIn('width=', rendered)

    def test_only_image_only_substack_cdn_wrappers_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            image='<img alt="Chart" src="/edition/assets/images/chart.png">'
            source='<a href="https://substackcdn.com/image/x">'+image+'</a><a href="https://example.test/source">'+image+'</a><a href="https://substackcdn.com/image/y">Read the source</a>'
            rendered=enhance_images(source,Path(directory),'/edition/')
            self.assertNotIn('href="https://substackcdn.com/image/x"',rendered)
            self.assertIn('href="https://example.test/source"',rendered)
            self.assertIn('href="https://substackcdn.com/image/y"',rendered)
            self.assertIn('<noscript><a href="/edition/assets/images/chart.png">Open original image</a></noscript>',rendered)

    def test_jpeg_dimensions_skip_application_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.jpeg'
            path.write_bytes(b'\xff\xd8\xff\xe0\x00\x04OK\xff\xc0\x00\x07\x08' + struct.pack('>HH', 240, 320))
            self.assertEqual(image_size(path), (320, 240))


if __name__ == '__main__': unittest.main()
