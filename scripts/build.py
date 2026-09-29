from __future__ import annotations
import argparse, hashlib, html, json, re, shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote
import xml.etree.ElementTree as ET
import markdown
from discovery import (article_schema, collection_schema, site_schema,
                       breadcrumb_schema, organisation_schema, social_meta, article_images, social_image)
from reading_media import enhance_images, IMAGE_VIEWER
from people import (load_profiles, profile_for, route as profile_route, authors,
                    contributions, enrich_article, profile_schema)
from release_gate import (editorial_fingerprint, validate_article_release,
                          previous_publication_dates, validate_training_policy)

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
TOPICS = {
 "government": ("Government & Public Services", "State capacity, public administration and the institutions that put technology to work."),
 "democracy": ("Democracy, Elections & Public Trust", "Information, accountability and the changing relationship between citizens and power."),
 "sovereignty": ("Power, Sovereignty & Geopolitics", "The infrastructure, capital and choices that determine who controls artificial intelligence."),
 "work": ("Work, Welfare & the Social Contract", "Automation, income, dignity and the distribution of technological gains."),
 "learning": ("Learning & Human Capability", "Education, judgement and the capabilities people need in a changing world."),
 "practice": ("AI in Practice", "Experiments, applications and lessons from using AI in public and institutional life."),
 "futures": ("Futures, Safety & Human Agency", "Possible futures, technological risk and the choices that remain ours to make.")
}
GENRES = {
    "analysis": "Analysis", "practical_experiment": "Practical experiment",
    "fiction": "Fiction", "review_or_commentary": "Review & commentary",
    "retrospective": "Retrospective", "report": "Report", "opinion": "Opinion",
    "essay": "Essay", "practical_guide": "Practical guide",
}
def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))
def e(value):
    return html.escape(str(value if value is not None else ""), quote=True)
def plain(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", text)).strip()
def author_name(record):
    return (record.get("author") or {}).get("name") or ""

def author_label(record):
    return author_name(record) or "Byline not stated in original"

def date_label(value):
    if not value: return "Date being verified"
    return datetime.fromisoformat(value[:10]).strftime("%d %B %Y").lstrip("0")
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=["review","public"],default="review")
    args=parser.parse_args()
    review=args.mode=="review"
    config=read_json(ROOT/"site.json")
    profiles=load_profiles(ROOT)
    script_path=ROOT/'assets/site.js'
    script_version=hashlib.sha256(script_path.read_bytes()).hexdigest()[:12] if script_path.exists() else '0'
    base=config["base_url"].rstrip("/")+"/"
    prefix=urlparse(base).path.rstrip("/")+"/"
    output=(ROOT/("preview" if review else "dist")).resolve()
    prior_dates=previous_publication_dates(output) if not review else {}
    training_check=None
    records=[]
    for path in sorted((ROOT/"content/en").glob("[0-9][0-9][0-9].json")):
        record=read_json(path)
        if not review and record.get("human_approval")!="approved": continue
        body_path=path.with_suffix(".md")
        if not body_path.exists(): raise ValueError("Missing translation: "+str(body_path))
        body_bytes=body_path.read_bytes()
        fingerprint=editorial_fingerprint(body_bytes, record)
        if not review:
            validate_article_release(record, body_bytes,
                                     prior_dates.get(f'{record["issue_number"]:03d}'))
        record["editorial_fingerprint"]=fingerprint
        record["raw"]=body_bytes.decode("utf-8-sig")
        record["id"]=f'{record["issue_number"]:03d}'
        record["route"]="essays/"+record["id"]+"/"
        record["url"]=base+record["route"]
        record['markdown_url']=base+'text/'+record['id']+'.md'
        if not record.get("topics") or any(t not in TOPICS for t in record["topics"]):
            raise ValueError("Invalid topic: "+str(path))
        record["minutes"]=max(1,round(len(record["raw"].split())/220))
        record["source_hash"]=hashlib.sha256(body_path.read_bytes()).hexdigest()
        record["search_text"]=html.unescape(plain(markdown.markdown(record["raw"])))
        record["word_count"]=len(record["search_text"].split())
        record["keywords"]=[TOPICS[t][0] for t in record["topics"]]
        record["genre_label"]=GENRES.get(record.get("genre"),"Essay")
        records.append(record)
    if not records: raise ValueError("No eligible translated essays.")
    if not review:
        if config.get("human_approval")!="approved":
            raise ValueError("Public release requires explicit editorial acceptance of the edition.")
        training_check=validate_training_policy(config, ROOT)
    # Only this generator's known output directories can be replaced.
    if output not in [(ROOT/"preview").resolve(),(ROOT/"dist").resolve()] or output.parent!=ROOT.resolve():
        raise ValueError("Unsafe output path")
    if output.exists() and not (output/"build-manifest.json").exists():
        raise ValueError("Output is not recognised as a generated build.")
    if output.exists(): shutil.rmtree(output)
    output.mkdir(parents=True)
    shutil.copytree(ROOT/"assets",output/"assets")
    def url(route=""):
        return prefix+route
    def write(route,content):
        target=output/route
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content,encoding="utf-8")
    def page(route,title,description,body,nav="",schema=None):
        canonical=base+route
        if schema is None:
            schema={"@context":"https://schema.org","@type":"AboutPage" if route=="about/" else "WebPage","@id":canonical+"#webpage","name":title,"description":description,"url":canonical,"inLanguage":"en-GB","isPartOf":{"@id":base+"#website"}}
        encoded=json.dumps(schema,ensure_ascii=False).replace("<","\\u003c")
        extra=[]
        if not route or route=="about/":
            extra.extend([site_schema(config,base),organisation_schema(config,base)])
        if route:
            crumbs=[("Home",base)]
            if route.startswith("essays/") and route!="essays/": crumbs.append(("Essays",base+"essays/"))
            if route.startswith("topics/") and route!="topics/": crumbs.append(("Topics",base+"topics/"))
            if route.startswith("people/") and route!="people/": crumbs.append(("People",base+"people/"))
            crumb_title=("Issue "+route.split("/")[1]) if schema.get("@type")=="Article" else title
            crumbs.append((crumb_title,canonical))
            extra.append(breadcrumb_schema(crumbs))
            body='<nav class="breadcrumbs" aria-label="Breadcrumb"><ol>'+''.join('<li>'+('<span aria-current="page">'+e(label)+'</span>' if i==len(crumbs)-1 else '<a href="'+e(urlparse(href).path)+'">'+e(label)+'</a>')+'</li>' for i,(label,href) in enumerate(crumbs))+'</ol></nav>'+body
        extra_json=''.join('<script type="application/ld+json">'+json.dumps(item,ensure_ascii=False).replace("<","\\u003c")+'</script>' for item in extra)
        alternate=('<link rel="alternate" type="text/markdown" title="Plain-text version" href="'+e(schema['encoding']['contentUrl'])+'">') if schema.get('@type')=='Article' and schema.get('encoding') else ''
        navigation="".join('<a href="'+url(dest)+'"'+(' aria-current="page"' if nav==label else '')+'>'+label+'</a>' for label,dest in [("Essays","essays/"),("Topics","topics/"),("About","about/")])
        banner=('<div class="review-banner">English edition · Editorial review copy. '
                '<a href="'+url("review/")+'">Review status</a></div>') if review else ""
        robot='<meta name="robots" content="noindex,nofollow">' if review or route=="404/" else '<meta name="robots" content="index,follow,max-image-preview:large">'
        full='''<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>'''+e(title)+''' · estrategIA</title><meta name="description" content="'''+e(description)+'''">
'''+robot+'''<link rel="canonical" href="'''+e(canonical)+'''">
'''+alternate+'''<link rel="sitemap" type="application/xml" href="'''+url('sitemap.xml')+'''">
'''+social_meta(title,description,canonical,config,base,is_article=schema.get("@type")=="Article",article_image=social_image(schema.get('image',[])) if schema.get('@type')=='Article' else None)+'''
<meta name="theme-color" content="#9d2235"><meta name="color-scheme" content="light">
<link rel="icon" href="'''+url("assets/favicon.svg")+'''" type="image/svg+xml">
<link rel="stylesheet" href="'''+url("assets/site.css")+'''"><script src="'''+url("assets/site.js")+'?v='+script_version+'''" defer></script>
<link rel="alternate" type="application/atom+xml" title="estrategIA English edition" href="'''+url("feed.xml")+'''">
<script type="application/ld+json">'''+encoded+'''</script>'''+extra_json+'''</head><body><a class="skip" href="#main">Skip to content</a>
'''+banner+'''<header class="wrap masthead"><div class="brand-block"><a class="brand" href="'''+url()+'''" aria-label="estrategIA home">estrateg<span>IA</span></a><span class="edition">English<br>edition</span></div><nav class="nav" aria-label="Main navigation">'''+navigation+'''<a class="spanish" href="https://estrategiabyaleph.substack.com">Read in Spanish</a></nav></header>
<main id="main" class="wrap" tabindex="-1">'''+body+'''</main>
<footer class="foot"><div class="wrap"><div class="foot-grid"><div><a class="brand" href="'''+url()+'''">estrateg<span>IA</span></a><p>Ideas about artificial intelligence, politics and government. From our Spanish archive, in English.</p></div><div><h2>Read</h2><ul><li><a href="'''+url("essays/")+'''">All essays</a></li><li><a href="'''+url("topics/")+'''">Explore topics</a></li><li><a href="https://estrategiabyaleph.substack.com/subscribe">Subscribe in Spanish</a></li></ul></div><div><h2>About this edition</h2><ul><li><a href="'''+url("about/")+'''">People and purpose</a></li><li><a href="'''+url("about/#translation-and-provenance")+'''">Translation and provenance</a></li><li><a href="'''+url("feed.xml")+'''">Follow new translations</a></li><li><a href="'''+url("catalog.json")+'''">Article catalogue</a></li><li><a href="'''+url("sitemap.xml")+'''">Sitemap</a></li></ul></div></div><div class="fineprint">© Institución Educativa ALEPH · Original publication dates are preserved. English translations retain the context of their Spanish originals.</div></div></footer></body></html>'''
        write(("index.html" if not route else route+"index.html"),full)
    def card(r,heading="h2"):
        t=r["topics"][0]
        search=" ".join([r["title"],r["description"],author_label(r),*r["keywords"],r["id"],r["genre_label"]])
        return '<article class="essay-card" data-essay data-id="'+r["id"]+'" data-number="'+str(r["issue_number"])+'" data-search="'+e(search)+'" data-topics="'+e(" ".join(r["topics"]))+'" data-genre="'+e(r.get("genre","essay"))+'" data-year="'+e((r.get("original_date") or "")[:4])+'"><div class="card-number"><span>Issue</span> '+r["id"]+'</div><div class="card-main"><div class="topic-label">'+e(TOPICS[t][0])+'</div><'+heading+'><a href="'+url(r["route"])+'">'+e(r["title"])+'</a></'+heading+'><p>'+e(r["description"])+'</p></div><div class="meta"><span class="card-author">'+e(author_label(r))+'</span><time datetime="'+e(r.get("original_date"))+'">'+date_label(r.get("original_date"))+'</time><span>'+str(r["minutes"])+' min read <span aria-hidden="true">·</span> '+e(r["genre_label"])+'</span></div></article>'
    def person_link(author):
        profile=profile_for(author,profiles)
        href=url(profile_route(profile)) if profile else author.get("url")
        name=author.get("name") or "Byline not stated in original"
        return '<a href="'+e(href)+'">'+e(name)+'</a>' if href else e(name)
    def team_cards():
        return '<div class="people-grid">'+''.join('<article class="person-card"><p class="eyebrow">'+e(p['role'])+'</p><h3><a href="'+url(profile_route(p))+'">'+e(p['name'])+'</a></h3><p>'+e(p['short_bio'])+'</p><a class="text-link" href="'+url(profile_route(p))+'">Profile and essays <span aria-hidden="true">→</span></a></article>' for p in profiles)+'</div>'
    records.sort(key=lambda r:r["issue_number"],reverse=True)
    lead=next((r for r in records if r["issue_number"]==155),records[0])
    years=sorted({r["original_date"][:4] for r in records if r.get("original_date")},reverse=True)
    period=(years[-1]+'–'+years[0]) if len(years)>1 else (years[0] if years else "")
    featured='''<section class="feature" aria-labelledby="featured-title"><div class="feature-main"><p class="eyebrow">Featured essay <span aria-hidden="true">/</span> Issue '''+lead["id"]+'''</p><h2 id="featured-title"><a href="'''+url(lead["route"])+'''">'''+e(lead["title"])+'''</a></h2><p class="summary">'''+e(lead["description"])+'''</p><div class="meta"><span>'''+e(author_label(lead))+'''</span><span>'''+str(lead["minutes"])+''' min read</span></div><a class="text-link" href="'''+url(lead["route"])+'''">Read the essay <span aria-hidden="true">↗</span></a></div><aside class="feature-aside"><p class="eyebrow">New to estrategIA?</p><h3>Start with a question.</h3><p>Who holds power? What can institutions do? How should the gains be shared?</p><p>Explore perspectives from the Spanish-language debate, with the author, date and original source always in view.</p><a class="text-link" href="'''+url("about/")+'''">Our people and purpose <span aria-hidden="true">↗</span></a></aside></section>'''
    home='''<section class="intro"><div><p class="eyebrow">The English edition</p><h1>AI, politics<br>and <em>government.</em></h1></div><div class="intro-copy"><p class="intro-lead">Technology changes what is possible.<br>Politics decides what comes next.</p><p>estrategIA explores how artificial intelligence is changing public life: the power to decide, the work we do and the institutions we share.</p><div class="intro-actions"><a class="button" href="'''+url("essays/")+'''">Explore the essays <span aria-hidden="true">→</span></a><a class="text-link" href="'''+url("topics/")+'''">Find a topic</a></div></div></section><div class="archive-facts" aria-label="About the archive"><span><strong>'''+str(len(records))+'''</strong> essays in English</span><span><strong>'''+str(len(TOPICS))+'''</strong> connected themes</span><span>Original essays <strong>'''+e(period)+'''</strong></span><a href="'''+url("about/#translation-and-provenance")+'''">From the Spanish originals <span aria-hidden="true">↗</span></a></div>'''+featured
    start=[next(r for r in records if r["issue_number"]==n) for n in [131,132,104] if any(r["issue_number"]==n for r in records)]
    if start:
        home+='<section aria-labelledby="start-title"><div class="section-heading"><div><p class="eyebrow">A place to begin</p><h2 id="start-title">Questions worth pursuing</h2></div><a href="'+url("essays/")+'">All '+str(len(records))+' essays <span aria-hidden="true">→</span></a></div><div class="essay-grid">'+"".join(card(r,"h3") for r in start)+'</div></section>'
    home+='<section aria-labelledby="ideas-title"><div class="section-heading"><div><p class="eyebrow">Follow an idea</p><h2 id="ideas-title">Seven ways into the debate</h2></div><a href="'+url("topics/")+'">Explore all topics <span aria-hidden="true">→</span></a></div><div class="topics-list">'
    for slug,(name,desc) in TOPICS.items():
        count=sum(slug in r["topics"] for r in records)
        home+='<a class="topic-row" href="'+url("topics/"+slug+"/")+'"><strong>'+e(name)+'</strong><span>'+str(count)+(' essay' if count==1 else ' essays')+' <span aria-hidden="true">↗</span></span></a>'
    home+='</div></section>'
    home+='<section aria-labelledby="recent-title"><div class="section-heading"><div><p class="eyebrow">From the original publication</p><h2 id="recent-title">The latest in the archive</h2></div><a href="'+url("essays/")+'">Browse the archive <span aria-hidden="true">→</span></a></div><div class="essay-grid">'+''.join(card(r,"h3") for r in records[:3])+'</div></section><section class="edition-note" aria-labelledby="edition-note-title"><h2 id="edition-note-title">A wider conversation. The same editorial care.</h2><p>Read each essay in full, follow its sources and return to the Spanish original. Translation brings the ideas to a new audience while preserving their voice and historical context.</p><a class="text-link" href="'+url("about/#translation-and-provenance")+'">How this edition is made <span aria-hidden="true">→</span></a></section>'
    home=home.replace('A wider conversation. The same editorial care.','Three years of ideas.<br>A wider conversation.').replace('Read each essay in full, follow its sources and return to the Spanish original. Translation brings the ideas to a new audience while preserving their voice and historical context.','Created to mark our third anniversary in October 2026, this archive translates only the newsletter’s main articles: ideas worth making accessible to readers around the world, with their original dates and voices intact. The full Spanish newsletter also includes news and a practical section with a tool of the week, prompts, a recommendation of the week and memes.').replace('How this edition is made','Why an English edition').replace(url('about/#translation-and-provenance')+'\">Why an English edition',url('about/#three-years-of-ideas-a-wider-conversation')+'\">Why an English edition')
    page("","AI, politics and government","The English edition of estrategIA: essays on artificial intelligence, public life and the power to decide.",home)
    available_genres=sorted({r.get("genre","essay") for r in records},key=lambda g:GENRES.get(g,g))
    filters='<form id="archive-filters" class="filters" role="search" aria-label="Search the essay archive" aria-busy="true"><label class="search-field" for="search">Search the full archive<input id="search" name="q" type="search" disabled placeholder="An idea, a phrase, an author…" autocomplete="off" aria-describedby="search-help"></label><p id="search-help" class="filter-help">Search titles, authors and the complete essay texts. If search is unavailable, browse all essays below.</p><div class="filter-options"><label for="topic">Topic<select id="topic" name="topic" disabled><option value="">All topics</option>'+''.join('<option value="'+k+'">'+e(v[0])+'</option>' for k,v in TOPICS.items())+'</select></label><label for="year">Original year<select id="year" name="year" disabled><option value="">All years</option>'+''.join('<option>'+y+'</option>' for y in years)+'</select></label><label for="genre">Type of essay<select id="genre" name="genre" disabled><option value="">All types</option>'+''.join('<option value="'+e(g)+'">'+e(GENRES.get(g,g))+'</option>' for g in available_genres)+'</select></label><label for="sort">Order<select id="sort" name="sort" disabled><option value="newest">Newest original first</option><option value="oldest">Oldest original first</option><option value="title">Title A–Z</option></select></label></div><div class="filter-actions"><button type="button" id="clear-filters" class="text-button" disabled>Clear filters</button><span>Share a search by copying its URL.</span></div><p id="search-status" class="status" role="status" aria-live="polite"></p></form><noscript><style>#archive-filters{display:none}</style><p class="history-note">All essays are listed below, newest first. Browser search is available; reading and topic navigation work without JavaScript.</p></noscript><p id="result-count" class="result-count" role="status" aria-live="polite">'+str(len(records))+' essays</p>'
    archive='<header class="page-heading"><p class="eyebrow">'+str(len(records))+' essays · '+e(period)+'</p><h1>Ideas to think with.</h1><p class="dek">Explore the English archive: arguments, experiments and possible futures for AI in public life. Dates refer to the Spanish originals.</p></header>'+filters+'<div id="archive-list" class="archive-list" data-search-index="'+url("search-index.json")+'">'+"".join(card(r) for r in records)+'</div><div id="empty-results" class="empty" hidden><h2>No essays found</h2><p>Try fewer words or clear a filter to broaden your search.</p></div><div class="load-more-wrap"><button type="button" id="load-more" class="button" hidden>Show more essays</button></div>'
    archive_description='Search '+str(len(records))+' English essays on AI, politics and government by topic, author, year and type. From the estrategIA archive.'
    page("essays/","Essays",archive_description,archive,"Essays",collection_schema("Essays",archive_description,base+"essays/",records,config,base))
    write("search-index.json",json.dumps({"articles":[{"id":r["id"],"text":" ".join([r["title"],r["description"],author_label(r),*r["keywords"],r["id"],r["genre_label"],r["search_text"]])} for r in records]},ensure_ascii=False,separators=(",",":")))
    topics='<header class="page-heading"><p class="eyebrow">Follow an idea</p><h1>Topics</h1><p class="dek">Seven ways into the public consequences of artificial intelligence.</p></header><div class="topics-list">'
    for slug,(name,desc) in TOPICS.items():
        selected=[r for r in records if slug in r["topics"]]
        topics+='<a class="topic-row topic-detail" href="'+url("topics/"+slug+"/")+'"><div><strong>'+e(name)+'</strong><p>'+e(desc)+'</p></div><span>'+str(len(selected))+' essays <span aria-hidden="true">↗</span></span></a>'
        inner='<header class="page-heading"><p class="eyebrow">A thread through the archive · '+str(len(selected))+' essays</p><h1>'+e(name)+'</h1><p class="dek">'+e(desc)+'</p><a class="text-link" href="'+url("essays/?topic="+slug)+'">Search within this topic <span aria-hidden="true">→</span></a></header>'
        inner+=('<div class="essay-grid">'+"".join(card(r) for r in selected)+'</div>') if selected else '<div class="empty"><p>Translations in this topic are being prepared. You can explore the complete original archive in Spanish.</p><a href="https://estrategiabyaleph.substack.com/archive">Read the Spanish archive</a></div>'
        page("topics/"+slug+"/",name,desc,inner,"Topics",collection_schema(name,desc,base+"topics/"+slug+"/",selected,config,base))
    page("topics/","Topics","Explore estrategIA by theme.",topics+'</div>',"Topics")
    about_md="""Artificial intelligence is changing more than software. It is changing how decisions are made, how public institutions work and how societies distribute knowledge, opportunity and power.

estrategIA is a Spanish-language publication about AI, politics, government, public communication and institutional leadership. Published weekly since October 2023, it connects technological change with questions that public leaders, researchers, communicators and citizens need to understand.

Our interest is in consequences: what a new capability makes possible, what it leaves unresolved, and which political or institutional choices follow. The archive brings together arguments, practical experiments and perspectives from Spain, Europe and Latin America. It makes room for technological ambition, scrutiny and human judgement.

## The people behind estrategIA

The publication was created and is directed by **[Fernando Nieto Lobato](https://www.fernandonieto.es/)**, its principal writer and Director of Digital Innovation at **[Institución Educativa ALEPH](https://institucioneducativaaleph.com/)**. **Pablo Martín Diez**, ALEPH's academic director, serves as editor, and **Sofía García Morales** works on editorial review and copy-editing.

Guest contributors bring their own expertise and arguments. Their articles retain their names and perspective; publication in this archive does not make every essay a collective institutional position.

## Why an English edition?

Many of the questions explored in estrategIA travel across borders. This edition makes the main essays available to readers who do not read Spanish, while keeping a clear link to the publication in which they first appeared.

You can begin with a theme, follow an author or browse the archive. Each essay can be read in full on its own page. The Spanish newsletter remains the original publication, with its wider selection of news, recommendations and practical resources.

## Translation and provenance

These translations aim to preserve the argument, voice and degree of certainty of the originals. They use international English with consistent British spelling. Institutions and culturally specific references are briefly explained where needed.

Every essay preserves its original publication date and Spanish source. Authors are credited where the original byline is known; unresolved attributions are identified explicitly. Historical claims and predictions retain their original context. A translation date is not an update of the argument. Any substantive correction or contextual addition is identified separately.

The preparation process uses AI for translation and an assisted bilingual review. Those steps are recorded separately from human editorial acceptance. Quotes translated from Spanish are not presented as independently verified original English wording unless they have been checked.

The reading pages, Markdown copies and article catalogue are generated from the same text. This makes the archive easier to consult and cite without creating a separate version for automated readers.

## Keep reading

The original newsletter is available on [Substack](https://estrategiabyaleph.substack.com). [Subscriptions are currently in Spanish](https://estrategiabyaleph.substack.com/subscribe).

For the original presentation of the publication and its editorial approach, [read the Spanish About page](https://estrategiabyaleph.substack.com/about).
"""
    about_path=ROOT/'content/site/about.md'
    if about_path.exists(): about_md=about_path.read_text(encoding='utf-8').replace('{{base_path}}',prefix)
    team='<section class="team-section" aria-labelledby="team-title"><div class="section-heading"><div><p class="eyebrow">The people behind the publication</p><h2 id="team-title">Meet the team</h2></div><a href="'+url('people/')+'">All profiles <span aria-hidden="true">→</span></a></div>'+team_cards()+'</section>' if profiles else ''
    about='<header class="page-heading"><p class="eyebrow">People, ideas and public life</p><h1>About estrategIA</h1><p class="dek">A Spanish publication. An international conversation.<br>Three years of thinking about AI and public life.</p></header><div class="about-layout"><div class="prose">'+markdown.markdown(about_md,extensions=["extra","toc"])+'</div><aside class="about-brand"><img src="'+url("assets/estrategia-header.png")+'" alt="The original estrategIA publication header" width="756" height="502"><p>An editorial initiative of Institución Educativa ALEPH.</p>'+('<a class="text-link" href="#team-title">Meet the team ↓</a>' if profiles else '')+'</aside></div>'+team
    page("about/","About estrategIA","The people, purpose and editorial method behind estrategIA's English edition.",about,"About")
    if profiles:
        page('people/','The people behind estrategIA','Meet the editorial team and contributors behind estrategIA, with English biographies and links to their essays.','<header class="page-heading"><p class="eyebrow">Ideas have authors</p><h1>The people behind estrategIA</h1><p class="dek">Meet the core editorial team and a regular contributor. The archive also includes guest authors, credited on each essay.</p></header>'+team_cards()+'<p class="people-context"><a href="'+url('about/')+'">Our purpose and editorial approach →</a></p>','About')
    for profile in profiles:
        selected=contributions(profile,records)
        links=''.join('<li><a href="'+e(link['url'])+'"'+(' hreflang="es"' if link['language']=='Spanish' else '')+'>'+e(link['label'])+' <span aria-hidden="true">↗</span></a><span class="link-language">'+e(link['language'])+'</span></li>' for link in profile['links'])
        bio=''.join('<p>'+e(paragraph)+'</p>' for paragraph in profile['bio'].split('\n\n'))
        content='<header class="page-heading profile-heading"><p class="eyebrow">'+e(profile['role'])+'</p><h1>'+e(profile['name'])+'</h1></header><div class="profile-layout"><div class="prose profile-bio">'+bio+'</div><aside class="profile-links" aria-label="More about '+e(profile['name'])+'"><h2>Elsewhere</h2><ul>'+links+'</ul><a class="text-link" href="'+url('people/')+'">Meet the team →</a></aside></div><section class="profile-essays" aria-labelledby="author-essays"><div class="section-heading"><div><p class="eyebrow">In the English archive</p><h2 id="author-essays">Essays by '+e(profile['name'])+'</h2><p>'+str(len(selected))+(' essay' if len(selected)==1 else ' essays')+', including co-authored work. Dates refer to the Spanish originals.</p></div></div><div class="archive-list">'+''.join(card(r) for r in selected)+'</div></section>'
        page(profile_route(profile),profile['name'],profile['short_bio'],content,'About',profile_schema(profile,selected,base))
    write('people.json',json.dumps({'people':[{'name':p['name'],'aliases':p['aliases'],'role':p['role'],'bio':p['bio'],'url':base+profile_route(p),'links':p['links'],'articles':[r['url'] for r in contributions(p,records)]} for p in profiles]},ensure_ascii=False,indent=2))
    catalogue=[]
    for r in records:
        raw=re.sub(r"^#\s+.+\r?\n", "",r["raw"],count=1).lstrip()
        def image_rewrite(match):
            alt,src=match.group(1),match.group(2)
            if src.startswith(("https://","http://")): return match.group(0)
            name=Path(unquote(src)).name
            candidates=[ROOT/src,ROOT/"assets/images"/name,PARENT/"corpus/issues/Attachments"/name]
            source=next((p for p in candidates if p.is_file()),None)
            if not source: raise ValueError("Missing article image: "+src)
            dest=output/"assets/images"/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,dest)
            return '!['+alt+']('+url("assets/images/"+name)+')'
        raw=re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",image_rewrite,raw)
        converter=markdown.Markdown(extensions=["extra","toc","sane_lists"],extension_configs={"toc":{"permalink":"¶","permalink_title":"Link to this section","toc_depth":"2-3"}})
        rendered=converter.convert(raw)
        rendered=rendered.replace('<table>', '<p class="table-hint">Scroll across the table to read all columns.</p><table tabindex="0" aria-label="Data table; scroll horizontally to read all columns">')
        if re.search(r"<(?:script|iframe|form)\b|\son\w+\s*=|javascript:",rendered,re.I):
            raise ValueError("Unsafe HTML in article "+r["id"])
        rendered=enhance_images(rendered,output,prefix)
        r['images']=article_images(rendered,base)
        for illustration in r['images']:
            image_path=output/unquote(urlparse(illustration['url']).path.removeprefix(prefix))
            illustration['contentSize']=str(image_path.stat().st_size)+' bytes'
        toc=converter.toc if converter.toc_tokens else ""
        genre=r["genre_label"]
        people=r.get("authors")
        if people:
            if not isinstance(people,list) or any(not isinstance(a,dict) or not isinstance(a.get("name"),str) or not a["name"].strip() for a in people):
                raise ValueError("Invalid coauthors for article "+r["id"])
            byline='; '.join(person_link(a) for a in people)
        else:
            byline=person_link(r.get('author') or {})
        byline_role="Authors" if people and len(people)>1 else "Author"
        headline='<header class="article-heading"><p class="eyebrow"><a href="'+url('topics/'+r['topics'][0]+'/')+'">'+e(TOPICS[r["topics"][0]][0])+'</a> · '+e(genre)+'</p><h1>'+e(r["title"])+'</h1><p class="dek">'+e(r["description"])+'</p><div class="article-meta"><div><strong>'+byline+'</strong><span>'+byline_role+'</span></div><div><strong><time datetime="'+e(r.get("original_date"))+'">'+date_label(r.get("original_date"))+'</time></strong><span>Originally published in Spanish</span></div><div><strong>'+str(r["minutes"])+' min read</strong><span>'+("English review draft" if review else "English edition · "+date_label(r["english_publication_date"]))+'</span></div></div></header>'
        historical='This is a translation of the original Spanish essay'+(' published on '+date_label(r["original_date"]) if r.get("original_date") else '')+'. Its claims, examples and forecasts retain that historical context.'
        citation=(author_name(r)+'. ' if author_name(r) else '')+'“'+r["title"]+'.” estrategIA, issue '+r["id"]+', '+date_label(r.get("original_date"))+'. English '+('translation, review draft' if review else 'edition, '+date_label(r["english_publication_date"]))+'. '+r["url"]
        body='<div class="article-body" id="essay-text">'+rendered+'<div class="history-note">'+e(historical)+' <a href="'+e(r["original_url"])+'" hreflang="es">Read the original Spanish edition</a>, including its accompanying illustrations.</div><section class="citation" aria-labelledby="cite-title"><h2 id="cite-title">Cite this essay</h2><p id="citation-text">'+e(citation)+'</p><button class="button" type="button" data-copy="citation-text" hidden>Copy citation</button><span class="status" role="status" aria-live="polite"></span></section><nav class="essay-topics" aria-label="Topics in this essay">'+''.join('<a href="'+url('topics/'+t+'/')+'">'+e(TOPICS[t][0])+'</a>' for t in r['topics'])+'</nav><a class="back-top" href="#main">Back to the top ↑</a></div>'
        aside='<aside class="article-aside" aria-label="Essay navigation">'+('<details class="reading-toc" open><summary>In this essay</summary>'+toc+'</details>' if toc else '<h2>Read and cite</h2>')+'<div class="aside-links"><a href="'+e(r["original_url"])+'" hreflang="es">Read in Spanish <span aria-hidden="true">↗</span></a><a href="#cite-title">Cite this essay</a><a href="'+url("text/"+r["id"]+".md")+'" type="text/markdown">Plain-text version <span class="file-kind">MD</span></a></div><p class="source-reminder">Translated from the Spanish original. Read in its original historical context.</p></aside>'
        related=[x for x in records if x["id"]!=r["id"]]
        related.sort(key=lambda x:len(set(x["topics"])&set(r["topics"])),reverse=True)
        more='<section class="related"><div class="section-heading"><h2>Continue the conversation</h2></div><div class="essay-grid">'+"".join(card(x,"h3") for x in related[:3])+'</div></section>'
        matched=[p for p in profiles if any(profile_for(a,[p]) for a in authors(r))]
        author_note=''.join('<aside class="author-note" aria-label="About '+e(p['name'])+'"><p class="eyebrow">'+('One of this essay’s co-authors' if people and len(people)>1 else 'About the author')+'</p><h2><a href="'+url(profile_route(p))+'">'+e(p['name'])+'</a></h2><p>'+e(p['short_bio'])+'</p><a class="text-link" href="'+url(profile_route(p))+'">Biography and essays →</a></aside>' for p in matched)
        schema=enrich_article(article_schema(r,config,base,review),r,profiles,base)
        page(r["route"],r["title"],r["description"],'<div id="reading-progress" aria-hidden="true"></div><article class="reading-article">'+headline+'<div class="article-layout">'+body+aside+'</div></article>'+author_note+more+IMAGE_VIEWER,"Essays",schema)
        export_header='# '+r["title"]+'\n\nAuthor: '+author_label(r)+'\nOriginal publication: '+str(r.get("original_date") or "unverified")+'\nSpanish original: '+r["original_url"]+'\nEnglish URL: '+r["url"]+'\nStatus: '+("Editorial review draft" if review else "Published translation")+'\n\n'+historical+'\n\n'
        if not review:
            export_header += "English publication: "+r["english_publication_date"]+"\n\n"
        # Absolute image URLs keep the plain-text copy portable.
        export_body=raw.replace(']('+prefix,']('+base)
        write("text/"+r["id"]+".md",export_header+export_body)
        catalogue.append({k:r.get(k) for k in ["id","issue_number","title","description","author","original_url","original_date","topics","genre","url"]}|{"inLanguage":"en-GB","markdown_url":base+"text/"+r["id"]+".md","english_publication_date":None if review else r["english_publication_date"],"english_modified_date":None if review else r.get("english_modified_date"),"status":"review_draft" if review else "published"})
        if people: catalogue[-1]["authors"]=people
        if matched: catalogue[-1]['author_profiles']=[base+profile_route(p) for p in matched]
    write("catalog.json",json.dumps({"title":config["title"],"status":"review_draft" if review else "published","articles":catalogue},ensure_ascii=False,indent=2))
    write("llms.txt","# estrategIA · English edition\n\n> Essays on AI, politics and government, translated from the Spanish publication.\n\n"+("This is an unpublished editorial review copy.\n\n" if review else "")+"This archive translates only the main articles. The original Spanish newsletter also includes news and a practical section with a tool of the week, prompts, a recommendation of the week and memes. Original dates and source links are retained. Historical analyses should not be read as current reporting.\n\n## Articles\n\n"+"".join("- ["+r["title"]+"]("+r["url"]+"): "+r["description"]+"\n" for r in records)+"\n## Resources\n\n- [Catalogue]("+base+"catalog.json)\n- [About]("+base+"about/)\n")
    routes=["","essays/","topics/","about/"]+["topics/"+x+"/" for x in TOPICS]+[r["route"] for r in records]
    if profiles:
        routes+=['people/']+[profile_route(p) for p in profiles]
        with (output/'llms.txt').open('a',encoding='utf-8') as handle:
            handle.write('\n## People and editorial context\n\n- [People](%speople/)\n- [Profiles catalogue](%speople.json)\n' % (base,base)+''.join('- ['+p['name']+']('+base+profile_route(p)+'): '+p['role']+'\n' for p in profiles))
    sitemap=ET.Element("urlset",xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for route in ([] if review else routes):
        node=ET.SubElement(sitemap,"url"); ET.SubElement(node,"loc").text=base+route
        article=next((r for r in records if r["route"]==route),None)
        if article: ET.SubElement(node,"lastmod").text=article.get("english_modified_date") or article["english_publication_date"]
    write("sitemap.xml",ET.tostring(sitemap,encoding="unicode",xml_declaration=True))
    feed=ET.Element("feed",xmlns="http://www.w3.org/2005/Atom")
    ET.SubElement(feed,"title").text=config["title"]
    ET.SubElement(feed,"id").text=base
    feed_date=(datetime.now(timezone.utc).date().isoformat() if review else
               max(r.get("english_modified_date") or r["english_publication_date"] for r in records))
    ET.SubElement(feed,"updated").text=feed_date+"T00:00:00Z"
    ET.SubElement(feed,"link",href=base+"feed.xml",rel="self")
    for r in ([] if review else records):
        entry=ET.SubElement(feed,"entry")
        ET.SubElement(entry,"title").text=r["title"]; ET.SubElement(entry,"id").text=r["url"]
        ET.SubElement(entry,"link",href=r["url"]); ET.SubElement(entry,"updated").text=(r.get("english_modified_date") or r["english_publication_date"])+"T00:00:00Z"
        ET.SubElement(entry,"published").text=r["english_publication_date"]+"T00:00:00Z"
        for person in r.get("authors") or [{"name":author_label(r)}]:
            author=ET.SubElement(entry,"author"); ET.SubElement(author,"name").text=person["name"]
            if person.get("url"): ET.SubElement(author,"uri").text=person["url"]
        ET.SubElement(entry,"summary").text=r["description"]
    write("feed.xml",ET.tostring(feed,encoding="unicode",xml_declaration=True))
    robots="# For a project subpath, the origin-level robots.txt remains authoritative.\nUser-agent: *\n"+("Disallow: /\n" if review else "Allow: /\nSitemap: "+base+"sitemap.xml\n")
    if not review and config["training_policy"]=="disallow": robots+="\nUser-agent: GPTBot\nDisallow: /\n"
    write("robots.txt",robots)
    page("404/","Page not found","This page is not available.",'<header class="page-heading"><p class="eyebrow">404</p><h1>That page is not here.</h1><p class="dek">Find your next reading in the <a href="'+url("essays/")+'">essay archive</a>.</p></header>')
    shutil.copyfile(output/"404/index.html",output/"404.html")
    if review:
        status='<header class="page-heading"><p class="eyebrow">Private editorial working copy</p><h1>Review this edition</h1><p class="dek">'+str(len(records))+' translations. This copy is not an approved publication. Automated checks, bilingual review and human acceptance are tracked separately.</p></header><table class="review-table"><thead><tr><th>Issue</th><th>Essay</th><th>Assisted review</th><th>Human acceptance</th></tr></thead><tbody>'
        for r in records: status+='<tr><td>'+r["id"]+'</td><td><a href="'+url(r["route"])+'">'+e(r["title"])+'</a></td><td>'+e(r.get("assisted_review_status","pending"))+'</td><td>'+e(r.get("human_approval","pending"))+'</td></tr>'
        page("review/","Editorial review","Review status for the English edition.",status+"</tbody></table>")
    manifest={"mode":args.mode,"base_url":base,"built_at":datetime.now(timezone.utc).isoformat(),"human_approval":config["human_approval"],"article_count":len(records),"article_ids":[r["id"] for r in records],"source_hashes":{r["id"]:r["source_hash"] for r in records},"files":sorted(str(p.relative_to(output)).replace("\\","/") for p in output.rglob("*") if p.is_file())}
    manifest["editorial_hashes"]={r["id"]:r["editorial_fingerprint"] for r in records}
    manifest['site_content_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'content/site').glob('*') if p.is_file()}
    manifest["english_publication_dates"]={} if review else {r["id"]:r["english_publication_date"] for r in records}
    manifest["training_policy_verification"]=training_check
    write("build-manifest.json",json.dumps(manifest,indent=2))
    print(json.dumps({"output":str(output),"mode":args.mode,"articles":len(records),"files":len(manifest["files"])}))
if __name__=="__main__": main()
