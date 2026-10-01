"""Resolve cross-references only to essays selected for this build."""
import html
import re
from urllib.parse import urlsplit


def key(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    path = parsed.path.rstrip('/')
    if host == 'open.substack.com' and path.startswith('/pub/estrategiabyaleph/p/'):
        path = path.removeprefix('/pub/estrategiabyaleph')
        host = 'estrategiabyaleph.substack.com'
    return host, path


def rewrite_references(rendered, records, prefix):
    destinations = {key(r['original_url']): prefix+r['route']
                    for r in records if r.get('original_url')}
    def replace(match):
        destination = destinations.get(key(html.unescape(match.group(2))))
        # The surrounding article header/source links are never passed here.
        # Spanish fragments cannot safely be applied to translated headings.
        return match.group(1)+html.escape(destination, quote=True)+match.group(3) if destination else match.group(0)
    return re.sub(r'(<a\b[^>]*\bhref=")([^"]+)(")', replace, rendered)
