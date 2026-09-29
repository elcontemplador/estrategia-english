"""Pure discovery metadata builders; release eligibility remains the caller's job.

These functions neither read files nor change records. They describe supplied
editorial facts, not approval, indexing, model access or guaranteed citations.
"""
from __future__ import annotations

import html
import mimetypes
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

CONTEXT = "https://schema.org"
LANGUAGE = "en-GB"
HEADER_IMAGE = "assets/estrategia-header.png"
HEADER_ALT = "estrategIA wordmark in white and burgundy on a dark background"


def article_images(rendered, base):
    """Describe only real, sufficiently large images in the visible article.

    No branding fallback: an essay without an illustration has no image claim.
    Dimensions are read from the existing local artwork by the reading renderer.
    """
    images = []
    seen = set()
    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag != 'img':
                return
            attrs = dict(attrs)
            src = attrs.get('src')
            if not src:
                return
            url = urljoin(base, src)
            try:
                width, height = int(attrs.get('width', 0)), int(attrs.get('height', 0))
            except (TypeError, ValueError):
                return
            if not url.startswith(base + 'assets/images/') or width * height < 50000 or url in seen:
                return
            seen.add(url)
            item = {'@type': 'ImageObject', 'url': url, 'contentUrl': url,
                    'width': width, 'height': height}
            if attrs.get('alt'):
                item['caption'] = attrs['alt']
            images.append(item)
    Parser().feed(rendered)
    return images


def _url(base, route=""):
    return urljoin(base.rstrip("/") + "/", route)


def _article_url(record, base):
    if record.get("url"):
        return _url(base, record["url"])
    if record.get("route"):
        return _url(base, record["route"])
    issue = record.get("id") or record.get("issue_number")
    if issue is None:
        raise ValueError("Article requires a URL, route or issue identifier")
    return _url(base, f"essays/{int(issue):03d}/")


def organisation_schema(config, base):
    """Describe the configured publisher without borrowing the edition's logo."""
    publisher = config.get("publisher") or {}
    if not publisher.get("name"):
        return {}
    result = {
        "@context": CONTEXT,
        "@type": "Organization",
        "@id": _url(base) + "#publisher",
        "name": publisher["name"],
    }
    if publisher.get("url"):
        result["url"] = publisher["url"]
    return result


def _publisher(config, base):
    return {k: v for k, v in organisation_schema(config, base).items()
            if k != "@context"}


def _person(person):
    if not person or not person.get("name"):
        return None
    # An editorial team is a collective author, not an invented person.
    kind = person.get("type", "Person")
    if kind not in {"Person", "Organization"}:
        raise ValueError("Author type must be Person or Organization")
    result = {"@type": kind, "name": person["name"]}
    if person.get("url"):
        result["url"] = person["url"]
    return result


def _periodical(config, base):
    result = {
        "@type": "Periodical",
        "@id": _url(base) + "#periodical",
        "name": config.get("title", "estrategIA · English edition"),
        "url": _url(base),
        "inLanguage": LANGUAGE,
    }
    if config.get("original_site"):
        result["translationOfWork"] = {
            "@type": "Periodical", "name": "estrategIA",
            "url": config["original_site"], "inLanguage": "es",
        }
    return result


def _word_count(record):
    """Prefer the caller's count; otherwise estimate readable Markdown words.

    This is deliberately a lightweight estimate, not a Markdown parser. Image
    URLs, link destinations and markup do not contribute; code text does.
    """
    explicit = record.get("word_count")
    if isinstance(explicit, int) and not isinstance(explicit, bool) and explicit >= 0:
        return explicit
    raw = record.get("raw")
    if not isinstance(raw, str) or not raw.strip():
        return None
    raw = re.sub(r"!\[[^\]]*\]\([^\n]*?\)", " ", raw)
    raw = re.sub(r"\[([^\]]+)\]\([^\n]*?\)", r"\1", raw)
    raw = re.sub(r"<[^>]*>", " ", raw)
    raw = re.sub(r"^\s*```[^\n]*$|^\s*~~~[^\n]*$", " ", raw, flags=re.M)
    return len(re.findall(r"\b\w+(?:[’'-]\w+)*\b", html.unescape(raw)))


def article_schema(record, config, base, review):
    """Return an Article object (not @graph), preserving the existing QA API.

    Original dates belong only to translationOfWork. Public English dates must
    come from this article, never the edition config or the current clock.
    """
    canonical = _article_url(record, base)
    result = {
        "@context": CONTEXT, "@type": "Article",
        "@id": canonical + "#article", "headline": record["title"],
        "description": record.get("description", ""), "url": canonical,
        "inLanguage": LANGUAGE,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "isPartOf": _periodical(config, base),
        "isAccessibleForFree": True,
    }
    if record.get('images'):
        result['image'] = record['images']
    if record.get('markdown_url'):
        result['encoding'] = {'@type': 'MediaObject', 'contentUrl': record['markdown_url'],
                              'encodingFormat': 'text/markdown', 'inLanguage': LANGUAGE}
    publisher = _publisher(config, base)
    if publisher:
        result["publisher"] = publisher
    authors = record.get("authors")
    if authors:
        people = [_person(person) for person in authors]
        if any(person is None for person in people):
            raise ValueError("Every coauthor must have an explicit name")
        result["author"] = people
    else:
        person = _person(record.get("author"))
        if person:
            result["author"] = person
    if record.get("original_url"):
        original = {
            "@type": "Article", "@id": record["original_url"],
            "url": record["original_url"], "inLanguage": "es",
        }
        if record.get("original_date"):
            original["datePublished"] = record["original_date"]
        result["translationOfWork"] = original
    if not review:
        published = record.get("english_publication_date") or record.get("publication_date")
        if published:
            result["datePublished"] = published
            if record.get("english_modified_date"):
                result["dateModified"] = record["english_modified_date"]
    genre = record.get("genre_label") or record.get("genre")
    if genre:
        result["genre"] = str(genre).replace("_", " ").title() if not record.get("genre_label") else genre
    keywords = record.get("keywords") or record.get("topics")
    if keywords:
        result["keywords"] = list(keywords) if isinstance(keywords, (list, tuple)) else keywords
    count = _word_count(record)
    if count is not None:
        result["wordCount"] = count
    return result


def collection_schema(title, description, canonical, records, config, base):
    """A collection in the caller's visible order, with URL-only list entries."""
    items = [{"@type": "ListItem", "position": position,
              "url": _article_url(record, base)}
             for position, record in enumerate(records, 1)]
    result = {
        "@context": CONTEXT, "@type": "CollectionPage",
        "@id": canonical + "#collection", "name": title,
        "description": description, "url": canonical, "inLanguage": LANGUAGE,
        "isPartOf": {"@type": "WebSite", "@id": _url(base) + "#website"},
        "mainEntity": {"@type": "ItemList", "numberOfItems": len(items),
                       "itemListElement": items},
    }
    publisher = _publisher(config, base)
    if publisher:
        result["publisher"] = publisher
    return result


def site_schema(config, base):
    result = {
        "@context": CONTEXT, "@type": "WebSite",
        "@id": _url(base) + "#website", "url": _url(base),
        "name": config.get("title", "estrategIA · English edition"),
        "inLanguage": LANGUAGE,
    }
    if config.get("tagline"):
        result["description"] = config["tagline"]
    publisher = _publisher(config, base)
    if publisher:
        result["publisher"] = publisher
    return result


def breadcrumb_schema(items):
    """Items are (visible label, absolute URL) pairs supplied by the page."""
    return {
        "@context": CONTEXT, "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": label, "item": url}
            for index, (label, url) in enumerate(items, 1)
        ],
    }


def social_meta(title, description, canonical, config, base, is_article=False, article_image=None):
    """HTML-escaped OG/Twitter tags using the existing editorial header image."""
    illustration = article_image or {}
    image = illustration.get('url') or _url(base, HEADER_IMAGE)
    image_type = mimetypes.guess_type(urlsplit(image).path)[0] or 'image/png'
    width = illustration.get('width') or 756
    height = illustration.get('height') or 502
    alt = illustration.get('caption') or (description if article_image else HEADER_ALT)
    tags = [
        ("property", "og:type", "article" if is_article else "website"),
        ("property", "og:title", title),
        ("property", "og:description", description),
        ("property", "og:url", canonical),
        ("property", "og:site_name", config.get("title", "estrategIA · English edition")),
        ("property", "og:locale", "en_GB"),
        ("property", "og:image", image),
        ("property", "og:image:type", image_type),
        ("property", "og:image:width", str(width)),
        ("property", "og:image:height", str(height)),
        ("property", "og:image:alt", alt),
        ("name", "twitter:card", "summary_large_image"),
        ("name", "twitter:title", title),
        ("name", "twitter:description", description),
        ("name", "twitter:image", image),
        ("name", "twitter:image:alt", alt),
    ]
    return "\n".join(
        f'<meta {attribute}="{key}" content="{html.escape(str(value or ""), quote=True)}">'
        for attribute, key, value in tags
    )
