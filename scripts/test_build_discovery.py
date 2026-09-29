"""Verify public/review discovery boundaries using fictional local records."""
import json
import unittest
import xml.etree.ElementTree as ET

import test_build_authorship as fixtures
from release_gate import editorial_fingerprint


class BuildDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AuthorshipBuildTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_public_dates_and_error_page_indexing(self):
        fixture = self.fixture
        fixture.article(1)
        path = fixture.root/'content/en/001.json'
        record = json.loads(path.read_text())
        record['english_modified_date'] = '2026-01-02'
        body = (fixture.root/'content/en/001.md').read_bytes()
        record['assisted_review_hash'] = record['human_approval_hash'] = editorial_fingerprint(body, record)
        path.write_text(json.dumps(record), encoding='utf-8')
        out = fixture.run_build('public')
        text, schema = fixture.schema(out, 1)
        self.assertIn('index,follow,max-image-preview:large', text)
        self.assertEqual(schema['datePublished'], '2026-01-01')
        self.assertEqual(schema['dateModified'], '2026-01-02')
        self.assertEqual(schema['translationOfWork']['datePublished'], '2025-01-01')
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        nodes = ET.parse(out/'sitemap.xml').findall('s:url', ns)
        dated = [(n.find('s:loc', ns).text, n.find('s:lastmod', ns).text)
                 for n in nodes if n.find('s:lastmod', ns) is not None]
        self.assertEqual(dated, [('https://example.test/archive/essays/001/', '2026-01-02')])
        self.assertIn('noindex,nofollow', (out/'404.html').read_text(encoding='utf-8'))
        self.assertFalse(any('/404/' in n.find('s:loc', ns).text for n in nodes))

    def test_review_is_private_and_search_text_is_separate(self):
        fixture = self.fixture
        fixture.article(1)
        out = fixture.run_build('review')
        for page in out.rglob('*.html'):
            self.assertIn('noindex,nofollow', page.read_text(encoding='utf-8'))
        self.assertEqual(len(list(ET.parse(out/'sitemap.xml').getroot())), 0)
        self.assertEqual(len(ET.parse(out/'feed.xml').findall('{http://www.w3.org/2005/Atom}entry')), 0)
        archive = (out/'essays/index.html').read_text(encoding='utf-8')
        self.assertNotIn('Synthetic content for a local test.', archive)
        self.assertIn('data-id="001"', archive)
        index = json.loads((out/'search-index.json').read_text(encoding='utf-8'))
        self.assertEqual(len(index['articles']), 1)
        self.assertIn('Synthetic content for a local test.', index['articles'][0]['text'])
        self.assertNotIn('datePublished', fixture.schema(out, 1)[1])


if __name__ == '__main__': unittest.main()
