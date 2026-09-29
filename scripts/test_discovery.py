"""Isolated discovery fixtures: no publication, remote calls or editorial edits."""
import copy
import json
import unittest
from html.parser import HTMLParser

from discovery import (article_schema, breadcrumb_schema, collection_schema,
                       organisation_schema, site_schema, social_meta)


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.base = "https://example.test/archive/"
        self.config = {
            "title": "estrategIA · English edition", "tagline": "AI & government",
            "publisher": {"name": "Test Publisher", "url": "https://publisher.test/"},
            "original_site": "https://spanish.test/", "publication_date": "1999-01-01",
        }
        self.record = {
            "issue_number": 7, "title": "A test essay", "description": "Test description",
            "author": {"name": "Test Author", "url": "https://author.test/profile"},
            "original_url": "https://spanish.test/essay", "original_date": "2025-01-02",
            "english_publication_date": "2026-02-03", "english_modified_date": "2026-03-04",
            "topics": ["government", "democracy"], "genre": "review_or_commentary",
            "raw": "# Heading\n\nSome [linked words](https://test.invalid/) and **text**.",
        }

    def schema(self, review=False):
        return article_schema(self.record, self.config, self.base, review)

    def test_review_omits_both_english_dates(self):
        result = self.schema(True)
        self.assertEqual(result["@type"], "Article")
        self.assertNotIn("@graph", result)
        self.assertNotIn("datePublished", result)
        self.assertNotIn("dateModified", result)
        self.assertEqual(result["translationOfWork"]["datePublished"], "2025-01-02")
        self.assertEqual(result["translationOfWork"]["inLanguage"], "es")

    def test_public_uses_article_dates_only(self):
        result = self.schema()
        self.assertEqual(result["datePublished"], "2026-02-03")
        self.assertEqual(result["dateModified"], "2026-03-04")
        self.record.pop("english_publication_date")
        self.record["publication_date"] = "2026-04-05"
        self.assertEqual(self.schema()["datePublished"], "2026-04-05")
        self.record.pop("publication_date")
        self.assertNotIn("datePublished", self.schema())
        self.assertNotIn("dateModified", self.schema())

    def test_person_url_is_preserved_and_never_fabricated(self):
        self.assertEqual(self.schema()["author"], {"@type": "Person", **self.record["author"]})
        self.record["author"]["url"] = None
        self.assertEqual(self.schema()["author"], {"@type": "Person", "name": "Test Author"})

    def test_collaborative_authors_keep_order_and_optional_urls(self):
        self.record["authors"] = [{"name": "B", "url": "https://test.invalid/b"}, {"name": "A", "url": None}]
        self.assertEqual(self.schema()["author"], [
            {"@type": "Person", "name": "B", "url": "https://test.invalid/b"},
            {"@type": "Person", "name": "A"},
        ])

    def test_unknown_author_is_omitted(self):
        for author in (None, {}, {"name": None, "url": None}):
            self.record["author"] = author
            self.assertNotIn("author", self.schema(True))

    def test_collective_credit_is_an_organisation_not_a_person(self):
        self.record["author"] = {"name": "Test editorial team", "url": None, "type": "Organization"}
        self.assertEqual(self.schema()["author"], {"@type": "Organization", "name": "Test editorial team"})

    def test_invalid_author_entity_type_is_rejected(self):
        self.record["author"]["type"] = "Article"
        with self.assertRaises(ValueError):
            self.schema()

    def test_invalid_coauthor_does_not_silently_disappear(self):
        self.record["authors"] = [{"name": "Known"}, {"name": None}]
        with self.assertRaises(ValueError):
            self.schema()

    def test_article_identity_and_edition_provenance(self):
        result = self.schema()
        url = self.base + "essays/007/"
        self.assertEqual(result["url"], url)
        self.assertEqual(result["@id"], url + "#article")
        self.assertEqual(result["mainEntityOfPage"]["@id"], url)
        edition = result["isPartOf"]
        self.assertEqual(edition["@type"], "Periodical")
        self.assertEqual(edition["translationOfWork"]["url"], self.config["original_site"])
        self.assertNotIn("sameAs", json.dumps(result))

    def test_caller_url_route_labels_and_word_count(self):
        self.record.update(url="https://example.test/chosen/", route="ignored/", word_count=987,
                           keywords=["Public services", "AI"], genre_label="Review or commentary")
        result = self.schema()
        self.assertEqual(result["url"], self.record["url"])
        self.assertEqual(result["wordCount"], 987)
        self.assertEqual(result["keywords"], self.record["keywords"])
        self.assertEqual(result["genre"], "Review or commentary")
        self.record.pop("url")
        self.assertEqual(self.schema()["url"], self.base + "ignored/")

    def test_markdown_word_count_is_a_simple_text_estimate(self):
        self.assertEqual(self.schema()["wordCount"], 6)
        self.record["raw"] += "\n![A picture](assets/image.png)"
        self.assertEqual(self.schema()["wordCount"], 6)
        self.record.pop("raw")
        self.assertNotIn("wordCount", self.schema())

    def test_absent_source_metadata_is_not_invented(self):
        self.record.pop("original_date")
        self.assertNotIn("datePublished", self.schema()["translationOfWork"])
        self.record.pop("original_url")
        self.assertNotIn("translationOfWork", self.schema())

    def test_collection_preserves_visible_order_and_url_only_entries(self):
        records = [{"issue_number": 9}, {"route": "essays/003/"}]
        result = collection_schema("Essays", "The archive", self.base + "essays/", records, self.config, self.base)
        self.assertEqual(result["@type"], "CollectionPage")
        self.assertEqual(result["mainEntity"]["numberOfItems"], 2)
        self.assertEqual(result["mainEntity"]["itemListElement"], [
            {"@type": "ListItem", "position": 1, "url": self.base + "essays/009/"},
            {"@type": "ListItem", "position": 2, "url": self.base + "essays/003/"},
        ])

    def test_empty_collection_is_honest(self):
        result = collection_schema("Empty", "Empty", self.base, [], {}, self.base)
        self.assertEqual(result["mainEntity"]["numberOfItems"], 0)
        self.assertEqual(result["mainEntity"]["itemListElement"], [])
        self.assertNotIn("publisher", result)

    def test_site_and_publisher_do_not_invent_logo_search_or_claims(self):
        org = organisation_schema(self.config, self.base)
        site = site_schema(self.config, self.base)
        self.assertEqual(org["name"], "Test Publisher")
        self.assertEqual(org["url"], "https://publisher.test/")
        self.assertEqual(site["publisher"]["@id"], org["@id"])
        self.assertEqual(site["inLanguage"], "en-GB")
        for key in ("logo", "sameAs", "potentialAction", "aggregateRating"):
            self.assertNotIn(key, org)
            self.assertNotIn(key, site)
        self.assertEqual(organisation_schema({}, self.base), {})

    def test_breadcrumbs_follow_supplied_labels_urls_and_order(self):
        pairs = [("Home", self.base), ("Essays & ideas", self.base + "essays/")]
        result = breadcrumb_schema(pairs)
        self.assertEqual(result["@type"], "BreadcrumbList")
        self.assertEqual(result["itemListElement"][1], {
            "@type": "ListItem", "position": 2, "name": "Essays & ideas", "item": pairs[1][1],
        })

    def test_social_meta_escapes_all_user_fields_without_new_elements(self):
        title = 'A "title" <script>alert(1)</script> & more'
        description = 'Apostrophe\'s > comparison'
        canonical = self.base + '?a=1&b="quoted"'
        parser = MetaParser()
        parser.feed(social_meta(title, description, canonical, self.config, self.base, True))
        self.assertEqual(len(parser.tags), 16)
        self.assertTrue(all(tag == "meta" and len(attrs) == 2 for tag, attrs in parser.tags))
        values = {attrs.get("property", attrs.get("name")): attrs["content"] for _, attrs in parser.tags}
        self.assertEqual(values["og:title"], title)
        self.assertEqual(values["twitter:description"], description)
        self.assertEqual(values["og:url"], canonical)
        self.assertEqual(values["og:type"], "article")
        self.assertEqual(values["og:image"], self.base + "assets/estrategia-header.png")
        self.assertEqual((values["og:image:width"], values["og:image:height"]), ("756", "502"))
        self.assertEqual(values["twitter:card"], "summary_large_image")
        self.assertIn('content="website"', social_meta(title, description, canonical, self.config, self.base))

    def test_builders_are_pure_and_json_serialisable(self):
        before = copy.deepcopy((self.record, self.config))
        json.dumps(self.schema(), ensure_ascii=False)
        site_schema(self.config, self.base)
        organisation_schema(self.config, self.base)
        self.assertEqual((self.record, self.config), before)


if __name__ == "__main__":
    unittest.main()
