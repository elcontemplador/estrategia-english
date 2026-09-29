"""Explicit editorial identities, separate from immutable article metadata."""
import json
import re
from pathlib import Path


def load_profiles(root):
    path = Path(root) / 'content/site/people.json'
    if not path.exists():
        return []
    profiles = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(profiles, list):
        raise ValueError('Profiles must be a list')
    names, slugs = set(), set()
    for p in profiles:
        if not isinstance(p, dict):
            raise ValueError('Each profile must be an object')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', p['slug']) or p['slug'] in slugs:
            raise ValueError('Invalid or duplicate profile slug')
        slugs.add(p['slug'])
        for key in ['name', 'role', 'bio', 'short_bio']:
            if not isinstance(p[key], str) or not p[key].strip():
                raise ValueError('Missing profile field: ' + key)
        if not isinstance(p.get('aliases'), list) or not p['aliases']:
            raise ValueError('Aliases must be a non-empty list')
        if p['name'] not in p['aliases']:
            raise ValueError('Profile name must be an explicit alias')
        for name in p['aliases']:
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ValueError('Ambiguous profile alias')
            names.add(name)
        for link in p['links']:
            if not link['url'].startswith(('https://', 'http://')):
                raise ValueError('Unsafe profile link')
    return profiles


def profile_for(author, profiles):
    if not author or author.get('type', 'Person') != 'Person':
        return None
    return next((p for p in profiles if author.get('name') in p['aliases']), None)


def route(profile):
    return 'people/' + profile['slug'] + '/'


def authors(record):
    return record.get('authors') or [record.get('author') or {}]


def contributions(profile, records):
    return [r for r in records if any(profile_for(a, [profile]) for a in authors(r))]


def author_entity(author, profiles, base):
    entity = {'@type': author.get('type', 'Person'), 'name': author['name']}
    p = profile_for(author, profiles)
    if p:
        entity.update({'@id': base + route(p) + '#person', 'url': base + route(p)})
    elif author.get('url'):
        entity['url'] = author['url']
    return entity


def enrich_article(schema, record, profiles, base):
    if record.get('authors'):
        schema['author'] = [author_entity(a, profiles, base) for a in record['authors']]
    elif (record.get('author') or {}).get('name'):
        schema['author'] = author_entity(record['author'], profiles, base)
    return schema


def profile_schema(profile, selected, base):
    canonical = base + route(profile)
    person = {'@type': 'Person', '@id': canonical + '#person', 'name': profile['name'],
              'url': canonical, 'description': profile['short_bio']}
    aliases = [a for a in profile['aliases'] if a != profile['name']]
    if aliases:
        person['alternateName'] = aliases
    # Only explicitly identified personal pages are identity links; publisher
    # team pages remain visible references rather than sameAs statements.
    same_as = [link['url'] for link in profile['links'] if link.get('identity')]
    if same_as:
        person['sameAs'] = same_as
    return {'@context': 'https://schema.org', '@type': 'ProfilePage',
            '@id': canonical + '#webpage', 'url': canonical,
            'name': profile['name'], 'description': profile['short_bio'],
            'inLanguage': 'en-GB', 'isPartOf': {'@id': base + '#website'},
            'mainEntity': person,
            'hasPart': [{'@type': 'Article', 'url': r['url'], 'name': r['title']} for r in selected]}
