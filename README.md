# estrategIA · English edition

An English reading edition of estrategIA, the Spanish-language publication about artificial intelligence, politics and government.

This repository contains the static website framework and the accepted deployment artifact. The English reading edition brings together 153 main articles from issues 001–156, with original dates, bylines and links to the Spanish newsletter. Editorial working files, source snapshots and review evidence are excluded from this repository. Articles enter a release only after editorial acceptance.

## Local editorial workflow

Use Python 3.11+ and install the pinned package in requirements.txt. Content and source images belong in the local editorial workspace described in AGENTS.md.

```text
python scripts/progress.py
python scripts/build.py --mode review
python scripts/serve.py
python scripts/qa.py --root preview
```

The progress report checks that recorded reviews match the current texts and keeps documented non-article exclusions separate from the translation backlog. It grants no approvals.

The server prints its local review URL. Review output is labelled and marked noindex. Browser checks additionally use an existing Playwright installation and Microsoft Edge.

Read EDITORIAL_GUIDE.md and GLOSSARY.md before preparing translations. A public build requires human acceptance in site.json and each article's metadata, resolved authorship, source dates and URLs, a passed independent bilingual review, matching review/approval fingerprints and a persistent English publication date per article. No command below grants approval.

```text
python scripts/build.py --mode public
python scripts/prepare_release.py
python scripts/verify_release.py
```

prepare_release.py runs the public HTML/export QA before staging dist/ into release/. It seals the exact output with checksums. After reviewing that artifact, explicitly stage it with git add -f release, commit and push. Select the manual “Publish approved English edition” workflow only for an accepted release. The workflow refuses absent, draft or changed artifacts and is never triggered by an ordinary push.

The production URL is https://elcontemplador.github.io/estrategia-english/. This is a free GitHub Pages project site. Its subdirectory robots.txt does not control elcontemplador.github.io. A GPTBot opt-out requires evidence of the effective origin-level policy before release; permitting access does not guarantee indexing or citations.

## Content model

Each translated essay has content/en/NNN.md and content/en/NNN.json. Metadata preserves source date, URL and author separately from translation dates and review state. Original source files are immutable. Unknown bylines remain null in the catalogue and are labelled explicitly in review pages; they never become invented Person records or a public release.

HTML, plain Markdown, JSON catalogue, sitemap and Atom feed are built from the same selected records. Full-text reading, topics and archive navigation work without JavaScript. With JavaScript, the archive initially shows 24 essays and offers more results on demand. Search downloads a separate full-text index only when needed; topic, year, genre and order are reflected in shareable URLs. If the index cannot be loaded, a labelled metadata-only fallback remains available with a retry control.

Reading pages provide a native section index, an optional image viewer and citation copying. Original artwork is preserved. Local image dimensions reserve its layout space, while lazy loading defers image downloads. No external fonts, analytics, UI libraries or AI services are required.

## Search and citation metadata

The generator supplies canonical URLs, social preview metadata and JSON-LD for articles, collections, breadcrumbs, the website and publisher. Spanish source dates belong to `translationOfWork`; public English publication and modification dates come from each accepted article. Sitemaps use those persistent dates rather than the build time. Error pages remain `noindex` in both modes.

`catalog.json`, per-essay Markdown and `llms.txt` remain alternative reading formats. They do not grant rights, guarantee inclusion in a search engine or guarantee AI citations. The full HTML is the primary reading surface. A reciprocal `hreflang` setup has not been claimed for the separately managed Spanish Substack; provenance is explicit instead.

Public framework files alone do not contain the private editorial workspace. A fresh clone cannot regenerate unpublished translations; it can verify and deploy a checked release once one has been committed.

## People and anniversary context

`content/site/about.md` explains the third-anniversary English archive and its relationship to the original Spanish newsletter. `content/site/people.json` holds sourced English biographies and explicit author-name aliases. These files belong to the local editorial workspace; source notes remain under `evidence/people-anniversary-2026-09-29/`.

The generator creates `/people/`, individual English profiles and `people.json`. It resolves article bylines to those profiles without altering article metadata or original attribution. Profile essay lists include named coauthors and use explicit aliases only; collective authors remain organisations. Article and profile structured data share the same person identifiers. Biographies, provenance and profile references also appear in the discovery resources. The build manifest records hashes of the site copy separately from article fingerprints.

The people directory separates the three explicitly designated editorial team members from guest authors. Every named guest and coauthor in the selected archive receives the same contribution page and an alphabetically ordered directory entry, regardless of affiliation. The registry preserves explicit aliases and existing profile routes; guests are discovered only from the articles eligible for that build, so unpublished contributors do not enter the public directory.

## Verification

```text
python -B -m unittest discover -s scripts -p "test_*.py"
python scripts/qa.py --root preview
python scripts/browser_qa.py
```

The last command needs the local review server running. It checks every generated route at 1440, 768 and 320 pixels, plus keyboard entry, 200% text sizing and reading without JavaScript. Use --mobile-issues followed by issue numbers to choose additional reading screenshots at 390 pixels, and --evidence to choose the local evidence folder. Technical checks do not replace assisted bilingual review or human editorial acceptance.

## Rights

Editorial content and brand assets retain their existing rights. Repository visibility is not a licence to republish third-party material.
