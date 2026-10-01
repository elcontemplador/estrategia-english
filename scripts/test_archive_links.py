import unittest
from archive_links import rewrite_references


class ArchiveLinkTests(unittest.TestCase):
    def test_only_selected_canonical_essays_change_and_fragments_are_not_invented(self):
        records=[{'original_url':'https://estrategiabyaleph.substack.com/p/test','route':'essays/033/'}]
        source='<a href="https://open.substack.com/pub/estrategiabyaleph/p/test?r=123&amp;utm_source=x#espanol">Read</a><a href="https://estrategiabyaleph.substack.com/p/untranslated">Other</a><a href="https://example.test/p/test">External</a>'
        result=rewrite_references(source,records,'/edition/')
        self.assertIn('href="/edition/essays/033/"',result)
        self.assertIn('href="https://estrategiabyaleph.substack.com/p/untranslated"',result)
        self.assertIn('href="https://example.test/p/test"',result)
        self.assertNotIn('#espanol',result)

    def test_unselected_and_unknown_urls_are_left_intact(self):
        source='<a href="https://estrategiabyaleph.substack.com/about">About</a><a href="https://substackcdn.com/image/foo">Image</a>'
        self.assertEqual(rewrite_references(source,[],'/edition/'),source)
