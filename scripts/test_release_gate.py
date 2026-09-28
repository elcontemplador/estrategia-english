"""Release guards: content drift, immutable dates and effective origin opt-out."""
from __future__ import annotations
import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from release_gate import (editorial_fingerprint, validate_article_release,
                          validate_training_policy, previous_publication_dates)


class ArticleGateTests(unittest.TestCase):
    def setUp(self):
        self.body = b"# A public question\n\nThe system may help; it does not prove fraud.\n"
        self.metadata = {
            "issue_number": 131, "title": "A public question",
            "description": "An argument about public scrutiny.",
            "author": {"name": "Example Author", "url": "https://example.org/author"},
            "original_url": "https://example.org/original",
            "original_date": "2026-04-01",
            "topics": ["democracy"], "genre": "analysis",
            "source_path": "content/es/131.md",
            "notes": ["The distinction between an alert and proof is preserved."],
            "translation_status": "draft", "assisted_review_status": "passed",
            "human_approval": "approved",
            "english_publication_date": "2026-10-04",
        }
        self.bind()

    def bind(self):
        fingerprint = editorial_fingerprint(self.body, self.metadata)
        self.metadata["assisted_review_hash"] = fingerprint
        self.metadata["human_approval_hash"] = fingerprint
        return fingerprint

    def test_bound_accepted_article_passes(self):
        self.assertEqual(validate_article_release(self.metadata, self.body), self.bind())

    def test_changed_modality_fails_even_when_flags_stay_approved(self):
        changed = self.body.replace(b"may help", b"proves fraud")
        with self.assertRaisesRegex(ValueError, "assisted review"):
            validate_article_release(self.metadata, changed)

    def test_every_editorial_change_invalidates_approval(self):
        changes = [
            ("title", "A changed claim"), ("description", "A stronger conclusion."),
            ("original_date", "2026-03-31"), ("original_url", "https://example.org/different"),
            ("author", {"name": "Different Author"}), ("topics", ["work"]),
            ("genre", "fiction"), ("notes", ["A changed source note."]),
            ("future_editorial_field", {"claim": "New material"}),
        ]
        for field, value in changes:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.metadata)
                changed[field] = value
                with self.assertRaisesRegex(ValueError, "assisted review"):
                    validate_article_release(changed, self.body)

    def test_workflow_updates_do_not_change_editorial_fingerprint(self):
        original = editorial_fingerprint(self.body, self.metadata)
        changed = dict(self.metadata,
                       translation_status="accepted",
                       human_approval="pending",
                       assisted_review_hash="stale",
                       human_approval_hash="stale",
                       translation_date="2026-09-30",
                       assisted_review_date="2026-10-01",
                       english_publication_date="2026-10-05",
                       assisted_review_evidence="evidence/another-path.md")
        self.assertEqual(original, editorial_fingerprint(self.body, changed))
        self.assertEqual(original, editorial_fingerprint(self.body, dict(reversed(list(self.metadata.items())))))

    def test_flags_alone_do_not_authorise_a_release(self):
        for field in ("assisted_review_hash", "human_approval_hash"):
            with self.subTest(field=field):
                changed = dict(self.metadata)
                changed.pop(field)
                with self.assertRaises(ValueError):
                    validate_article_release(changed, self.body)

    def test_hashes_do_not_override_pending_human_or_assisted_status(self):
        for field, value in (("human_approval", "pending"), ("assisted_review_status", "pending")):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    validate_article_release(dict(self.metadata, **{field: value}), self.body)

    def test_english_date_is_required_and_valid(self):
        for value in (None, "", "tomorrow", "2026-02-30", "2025-01-01", "2026-10-04T00:00:00Z"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_article_release(dict(self.metadata, english_publication_date=value), self.body)

    def test_prior_first_publication_date_cannot_be_rewritten(self):
        changed = dict(self.metadata, english_publication_date="2026-10-11")
        with self.assertRaisesRegex(ValueError, "cannot change"):
            validate_article_release(changed, self.body, previous_english_date="2026-10-04")
        validate_article_release(self.metadata, self.body, previous_english_date="2026-10-04")

    def test_modified_date_cannot_precede_publication(self):
        with self.assertRaisesRegex(ValueError, "modified date"):
            validate_article_release(dict(self.metadata, english_modified_date="2026-10-03"), self.body)
        validate_article_release(dict(self.metadata, english_modified_date="2026-10-05"), self.body)

    def test_prior_catalogue_preserves_dates_across_new_lots(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            (output / "build-manifest.json").write_text('{"mode":"public"}', encoding="utf-8")
            (output / "catalog.json").write_text(json.dumps({"articles": [
                {"id": "131", "english_publication_date": "2026-10-04"},
                {"id": "155", "english_publication_date": "2026-10-11"}]}), encoding="utf-8")
            self.assertEqual(previous_publication_dates(output), {
                "131": "2026-10-04", "155": "2026-10-11"})
            (output / "catalog.json").unlink()
            with self.assertRaisesRegex(ValueError, "no catalogue"):
                previous_publication_dates(output)


class TrainingGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "evidence").mkdir()
        self.now = datetime(2026, 9, 28, 20, 0, tzinfo=timezone.utc)
        self.config = {
            "base_url": "https://example.github.io/estrategia-english/",
            "training_policy": "disallow",
            "origin_robots_evidence": "evidence/origin-robots.json",
        }
        self.body = "User-agent: GPTBot\nDisallow: /estrategia-english/\n"
        self.evidence = {
            "url": "https://example.github.io/robots.txt",
            "final_url": "https://example.github.io/robots.txt",
            "http_status": 200, "content_type": "text/plain; charset=utf-8",
            "retrieved_at": (self.now-timedelta(hours=1)).isoformat(),
            "body": self.body,
            "body_sha256": hashlib.sha256(self.body.encode()).hexdigest(),
        }
        self.write_evidence()

    def tearDown(self): self.temp.cleanup()

    def write_evidence(self):
        (self.root / self.config["origin_robots_evidence"]).write_text(
            json.dumps(self.evidence), encoding="utf-8")

    def validate(self, config=None):
        return validate_training_policy(config or self.config, self.root, self.now)

    def test_allow_needs_no_robot_evidence_and_promises_no_indexing(self):
        result = self.validate({"base_url": self.config["base_url"], "training_policy": "allow"})
        self.assertFalse(result["indexing_guaranteed"])

    def test_project_robots_alone_cannot_authorise_disallow(self):
        with self.assertRaisesRegex(ValueError, "origin /robots.txt"):
            self.validate({"base_url": self.config["base_url"], "training_policy": "disallow"})

    def test_verified_exact_origin_response_can_authorise_subpath_opt_out(self):
        result = self.validate()
        self.assertEqual(result["scope"], "verified_origin_robots")
        self.assertFalse(result["indexing_guaranteed"])

    def test_wrong_response_html_and_body_tampering_are_rejected(self):
        changes = [
            ("url", self.config["base_url"]+"robots.txt"),
            ("final_url", "https://another.example/robots.txt"),
            ("http_status", 404), ("content_type", "text/html"),
            ("body", "User-agent: GPTBot\nAllow: /\n"),
            ("body_sha256", "0"*64),
        ]
        original = dict(self.evidence)
        for key, value in changes:
            with self.subTest(field=key):
                self.evidence = dict(original, **{key: value})
                self.write_evidence()
                with self.assertRaises(ValueError): self.validate()

    def test_expired_future_and_naive_evidence_times_are_rejected(self):
        times = [(self.now-timedelta(hours=25)).isoformat(),
                 (self.now+timedelta(minutes=1)).isoformat(),
                 "2026-09-28T19:00:00"]
        for timestamp in times:
            with self.subTest(timestamp=timestamp):
                self.evidence["retrieved_at"] = timestamp
                self.write_evidence()
                with self.assertRaises(ValueError): self.validate()

    def test_irrelevant_or_partial_block_and_allow_exceptions_are_rejected(self):
        invalid = [
            "User-agent: OtherBot\nDisallow: /\n",
            "User-agent: GPTBot\nDisallow: /estrategia-english/private/\n",
            "User-agent: GPTBot\nDisallow: /\nAllow: /estrategia-english/text/\n",
            "User-agent: GPTBot\nDisallow: /*\n",
            "User-agent: GPTBot\n\nUser-agent: OtherBot\nDisallow: /\n",
            "User-agent: GPTBot\nCrawl-delay: 1\nUser-agent: OtherBot\nDisallow: /\n",
        ]
        for body in invalid:
            with self.subTest(body=body):
                self.evidence["body"] = body
                self.evidence["body_sha256"] = hashlib.sha256(body.encode()).hexdigest()
                self.write_evidence()
                with self.assertRaises(ValueError): self.validate()

    def test_evidence_outside_internal_directory_is_rejected(self):
        config = dict(self.config, origin_robots_evidence="outside.json")
        with self.assertRaisesRegex(ValueError, "evidence directory"):
            self.validate(config)


if __name__ == "__main__":
    unittest.main()
