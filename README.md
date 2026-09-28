# estrategIA · English edition

An English reading edition of estrategIA, the Spanish-language publication about artificial intelligence, politics and government.

This repository contains the static website framework. The translation archive is expanding in chronological batches under local editorial review; the public reading site has not been launched. Editorial working files, source snapshots and review evidence are excluded from this repository. Articles enter a release only after editorial acceptance.

## Local editorial workflow

Use Python 3.11+ and install the pinned package in requirements.txt. Content and source images belong in the local editorial workspace described in AGENTS.md.

```text
python scripts/build.py --mode review
python scripts/serve.py
python scripts/qa.py --root preview
```

The server prints its local review URL. Review output is labelled and marked noindex. Browser checks additionally use an existing Playwright installation and Microsoft Edge.

Read EDITORIAL_GUIDE.md and GLOSSARY.md before preparing translations. A public build requires human acceptance in site.json and each article's metadata, source dates and URLs, a passed independent bilingual review, matching review/approval fingerprints and a persistent English publication date per article. No command below grants approval.

```text
python scripts/build.py --mode public
python scripts/prepare_release.py
python scripts/verify_release.py
```

prepare_release.py runs the public HTML/export QA before staging dist/ into release/. It seals the exact output with checksums. After reviewing that artifact, explicitly stage it with git add -f release, commit and push. Select the manual “Publish approved English edition” workflow only for an accepted release. The workflow refuses absent, draft or changed artifacts and is never triggered by an ordinary push.

The planned production URL is https://elcontemplador.github.io/estrategia-english/. This is a free GitHub Pages project site. Its subdirectory robots.txt does not control elcontemplador.github.io. A GPTBot opt-out requires evidence of the effective origin-level policy before release; permitting access does not guarantee indexing or citations.

## Content model

Each translated essay has content/en/NNN.md and content/en/NNN.json. Metadata preserves source date, URL and author separately from translation dates and review state. Original source files are immutable.

HTML, plain Markdown, JSON catalogue, sitemap and Atom feed are built from the same selected records. Full-text reading, topics and archive navigation work without JavaScript. Search and interactive filters use a small local script.

Public framework files alone do not contain the private editorial workspace. A fresh clone cannot regenerate unpublished translations; it can verify and deploy a checked release once one has been committed.

## Verification

```text
python -B -m unittest discover -s scripts -p "test_*.py"
python scripts/qa.py --root preview
python scripts/browser_qa.py
```

The last command needs the local review server running. Technical checks do not replace assisted bilingual review or human editorial acceptance.

## Rights

Editorial content and brand assets retain their existing rights. Repository visibility is not a licence to republish third-party material.
