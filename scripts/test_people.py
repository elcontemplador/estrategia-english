"""Independent profile identity/release regressions using isolated build fixtures."""
import copy
import json
import re
import unittest
import xml.etree.ElementTree as ET

import test_build_authorship as fixtures
from people import load_profiles, profile_for, profile_schema
from release_gate import editorial_fingerprint


class PeopleBuildTests(unittest.TestCase):
    # Reuse only fixture helpers, not the existing authorship test cases.
    setUp = fixtures.AuthorshipBuildTests.setUp
    tearDown = fixtures.AuthorshipBuildTests.tearDown
    article = fixtures.AuthorshipBuildTests.article
    run_build = fixtures.AuthorshipBuildTests.run_build
    schema = fixtures.AuthorshipBuildTests.schema

    def profile(self, name='Gabriela Ortega Jarr\u00edn', slug='gabriela-ortega', aliases=None):
        return {
            'slug': slug, 'name': name, 'aliases': aliases or [name],
            'role': 'Fictional fixture role',
            'bio': 'Synthetic biography for isolated testing only.',
            'short_bio': 'Synthetic test biography.',
            'links': [{'label': 'Test reference', 'url': 'https://example.test/reference',
                       'language': 'English'}],
        }

    def save_profiles(self, profiles):
        path = self.root / 'content/site/people.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(profiles), encoding='utf-8')

    def update_article(self, number, **changes):
        path = self.root / f'content/en/{number:03}.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record.update(changes)
        fingerprint = editorial_fingerprint(path.with_suffix('.md').read_bytes(), record)
        record['assisted_review_hash'] = record['human_approval_hash'] = fingerprint
        path.write_text(json.dumps(record), encoding='utf-8')

    def profile_output(self, output, slug):
        text = (output / f'people/{slug}/index.html').read_text(encoding='utf-8')
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',
                                     text, re.S).group(1))
        return text, schema

    def test_explicit_aliases_share_entity_without_rewriting_historical_metadata(self):
        profile = self.profile(aliases=['Gabriela Ortega Jarr\u00edn', 'Gabriela Ortega'])
        self.save_profiles([profile])
        for number, name in [(33, 'Gabriela Ortega'), (88, 'Gabriela Ortega Jarr\u00edn')]:
            self.article(number)
            self.update_article(number, author={
                'name': name, 'url': f'https://example.test/historical/{number}', 'type': 'Person'})
        originals = {path: path.read_bytes() for path in (self.root / 'content/en').iterdir()}
        output = self.run_build('public')
        person_id = 'https://example.test/archive/people/gabriela-ortega/#person'
        for number, name in [(33, 'Gabriela Ortega'), (88, 'Gabriela Ortega Jarr\u00edn')]:
            text, article = self.schema(output, number)
            self.assertEqual(article['author']['@id'], person_id)
            self.assertEqual(article['author']['name'], name)
            self.assertEqual(article['@id'], f'https://example.test/archive/essays/{number:03}/#article')
            heading = text.split('<header class="article-heading">')[1].split('</header>')[0]
            self.assertIn(f'>{name}</a>', heading)
            self.assertIn('/archive/people/gabriela-ortega/', heading)
        _, page = self.profile_output(output, 'gabriela-ortega')
        self.assertEqual(page['@type'], 'ProfilePage')
        self.assertEqual(page['mainEntity']['@id'], person_id)
        self.assertEqual(page['mainEntity']['alternateName'], ['Gabriela Ortega'])
        expected = {'https://example.test/archive/essays/033/',
                    'https://example.test/archive/essays/088/'}
        self.assertEqual({part['url'] for part in page['hasPart']}, expected)
        catalogue = json.loads((output / 'catalog.json').read_text(encoding='utf-8'))['articles']
        for record in catalogue:
            self.assertEqual(record['author']['url'],
                             f'https://example.test/historical/{record["issue_number"]}')
        for path, contents in originals.items():
            self.assertEqual(path.read_bytes(), contents)

    def test_organisation_with_matching_name_does_not_become_profile_person(self):
        self.save_profiles([self.profile('Editorial Group', 'editorial-group')])
        self.article(32)
        organisation = {'name': 'Editorial Group', 'type': 'Organization',
                        'url': 'https://example.test/organisation/'}
        self.update_article(32, author=organisation)
        output = self.run_build('review')
        text, article = self.schema(output, 32)
        self.assertEqual(article['author'], {'@type': 'Organization', 'name': organisation['name'],
                                            'url': organisation['url']})
        self.assertNotIn('class="author-note"', text)
        self.assertEqual(self.profile_output(output, 'editorial-group')[1]['hasPart'], [])
        self.assertIsNone(profile_for(organisation, load_profiles(self.root)))

    def test_profiles_select_only_explicit_members_of_eight_coauthors(self):
        people = [{'name': f'Synthetic author {i}', 'url': f'https://example.test/person/{i}'}
                  for i in range(1, 9)]
        self.save_profiles([
            self.profile(people[0]['name'], 'first-author'),
            self.profile(people[6]['name'], 'seventh-author'),
            self.profile('Unrelated editor', 'unrelated-editor'),
        ])
        self.article(130, people)
        self.article(129)
        self.update_article(129, author={'name': 'Unrelated editor', 'url': None})
        output = self.run_build('review')
        _, article = self.schema(output, 130)
        self.assertEqual([author['name'] for author in article['author']],
                         [author['name'] for author in people])
        self.assertEqual([i for i, author in enumerate(article['author']) if '@id' in author], [0, 6])
        for slug in ['first-author', 'seventh-author']:
            page = self.profile_output(output, slug)[1]
            self.assertEqual([part['url'] for part in page['hasPart']],
                             ['https://example.test/archive/essays/130/'])
        page = self.profile_output(output, 'unrelated-editor')[1]
        self.assertEqual([part['url'] for part in page['hasPart']],
                         ['https://example.test/archive/essays/129/'])
        _, schema129 = self.schema(output, 129)
        self.assertEqual(schema129['author']['@id'],
                         'https://example.test/archive/people/unrelated-editor/#person')
        self.assertNotIn('https://example.test/archive/people/unrelated-editor/#person',
                         json.dumps(article['author']))

    def test_profile_lists_and_sitemap_respect_article_release_gates(self):
        profile = self.profile('Single test author', 'test-author')
        self.save_profiles([profile])
        self.article(1)
        self.article(2)
        self.update_article(2, human_approval='pending', english_publication_date=None)
        public = self.run_build('public')
        _, published_profile = self.profile_output(public, 'test-author')
        self.assertEqual([entry['url'] for entry in published_profile['hasPart']],
                         ['https://example.test/archive/essays/001/'])
        exported = json.loads((public / 'people.json').read_text(encoding='utf-8'))['people'][0]
        self.assertEqual(exported['articles'], ['https://example.test/archive/essays/001/'])
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        public_urls = [node.text for node in ET.parse(public / 'sitemap.xml').findall('s:url/s:loc', ns)]
        self.assertIn('https://example.test/archive/people/', public_urls)
        self.assertIn('https://example.test/archive/people/test-author/', public_urls)
        self.assertNotIn('https://example.test/archive/essays/002/', public_urls)
        self.assertFalse((public / 'essays/002/index.html').exists())
        review = self.run_build('review')
        text, review_profile = self.profile_output(review, 'test-author')
        self.assertEqual(len(review_profile['hasPart']), 2)
        self.assertIn('noindex', text)
        self.assertEqual(ET.parse(review / 'sitemap.xml').findall('s:url', ns), [])
        self.assertIn('Disallow: /', (review / 'robots.txt').read_text(encoding='utf-8'))
        self.assertEqual(json.loads((self.root / 'content/en/002.json').read_text())['human_approval'],
                         'pending')

    def test_profiles_do_not_bypass_edition_editorial_acceptance(self):
        self.save_profiles([self.profile('Single test author', 'test-author')])
        self.article(1)
        config_path = self.root / 'site.json'
        config = json.loads(config_path.read_text(encoding='utf-8'))
        config['human_approval'] = 'pending'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'explicit editorial acceptance'):
            self.run_build('public')
        self.assertFalse((self.root / 'dist').exists())

    def test_matching_never_infers_undeclared_name_variants(self):
        profile = self.profile(aliases=['Gabriela Ortega Jarr\u00edn', 'Gabriela Ortega'])
        original = copy.deepcopy(profile)
        for name in ['Gabriela', 'Gabriela Ortega Jarrin', 'gabriela ortega',
                     'Mar\u00eda Gabriela Ortega Jarr\u00edn']:
            with self.subTest(name=name):
                self.assertIsNone(profile_for({'name': name}, [profile]))
        self.assertEqual(profile, original)

    def test_invalid_aliases_are_rejected_including_string_substring_trap(self):
        for aliases in ['Ada', [], ['Other'], ['Ada', 'Ada'], ['Ada', None], ['Ada', '']]:
            with self.subTest(aliases=aliases):
                profile = self.profile('Ada', 'ada')
                profile['aliases'] = aliases
                self.save_profiles([profile])
                with self.assertRaises(ValueError):
                    load_profiles(self.root)
        self.save_profiles([
            self.profile('Ada', 'ada', ['Ada', 'Shared']),
            self.profile('Bea', 'bea', ['Bea', 'Shared']),
        ])
        with self.assertRaises(ValueError):
            load_profiles(self.root)

    def test_invalid_or_duplicate_slugs_cannot_create_profile_routes(self):
        for slug in ['', '../ada', 'Ada', 'ada/', '\u00e1da', 'ada--profile']:
            with self.subTest(slug=slug):
                self.save_profiles([self.profile('Ada', slug)])
                with self.assertRaises(ValueError):
                    load_profiles(self.root)
        self.save_profiles([self.profile('Ada', 'same'), self.profile('Bea', 'same')])
        with self.assertRaises(ValueError):
            load_profiles(self.root)

    def test_sameas_uses_only_explicit_identity_links_not_team_references(self):
        profile = self.profile()
        profile['links'] = [
            {'label': 'Personal', 'url': 'https://example.test/person/', 'identity': True},
            {'label': 'Team', 'url': 'https://example.test/team/'},
            {'label': 'Reference', 'url': 'https://example.test/work/', 'identity': False},
        ]
        page = profile_schema(profile, [], 'https://example.test/archive/')
        self.assertEqual(page['mainEntity']['sameAs'], ['https://example.test/person/'])
        profile['links'][0]['identity'] = False
        self.assertNotIn('sameAs', profile_schema(profile, [], 'https://example.test/archive/')['mainEntity'])


if __name__ == '__main__':
    unittest.main()
