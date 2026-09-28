import hashlib, json, tempfile, unittest
from pathlib import Path
from verify_release import verify

class ReleaseArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "build-manifest.json").write_text(json.dumps({"mode":"public","human_approval":"approved","article_count":1}), encoding="utf-8")
        (self.root / "catalog.json").write_text(json.dumps({"status":"published","articles":[{"status":"published","english_publication_date":"2026-10-01"}]}), encoding="utf-8")
        (self.root / "index.html").write_text('<meta name="robots" content="index,follow">', encoding="utf-8")
        self.seal()
    def tearDown(self): self.tmp.cleanup()
    def seal(self):
        files = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir() if p.name!="release-checksums.json"}
        (self.root / "release-checksums.json").write_text(json.dumps(files), encoding="utf-8")
    def test_accepted_unchanged_artifact(self):
        self.assertEqual(verify(self.root)["article_count"],1)
    def test_changed_html_rejected(self):
        (self.root/"index.html").write_text("changed after review",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"checksum"): verify(self.root)
    def test_extra_file_rejected(self):
        (self.root/"private.txt").write_text("must not be deployed",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"files changed"): verify(self.root)
    def test_review_page_rejected_even_if_sealed(self):
        (self.root/"index.html").write_text('<meta name="robots" content="noindex,nofollow">',encoding="utf-8")
        self.seal()
        with self.assertRaisesRegex(ValueError,"Review page"): verify(self.root)
    def test_review_manifest_rejected(self):
        (self.root/"build-manifest.json").write_text(json.dumps({"mode":"review","human_approval":"pending","article_count":1}),encoding="utf-8")
        self.seal()
        with self.assertRaisesRegex(ValueError,"accepted public"): verify(self.root)
if __name__=="__main__": unittest.main()
