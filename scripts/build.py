from __future__ import annotations
import argparse, hashlib, html, json, re, shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote
import xml.etree.ElementTree as ET
import markdown
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
        if not record.get("topics") or any(t not in TOPICS for t in record["topics"]):
            raise ValueError("Invalid topic: "+str(path))
        record["minutes"]=max(1,round(len(record["raw"].split())/220))
        record["source_hash"]=hashlib.sha256(body_path.read_bytes()).hexdigest()
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
            schema={"@context":"https://schema.org","@type":"WebPage","name":title,"url":canonical,"inLanguage":"en-GB"}
        encoded=json.dumps(schema,ensure_ascii=False).replace("<","\\u003c")
        navigation="".join('<a href="'+url(dest)+'"'+(' aria-current="page"' if nav==label else '')+'>'+label+'</a>' for label,dest in [("Essays","essays/"),("Topics","topics/"),("About","about/")])
        banner=('<div class="review-banner">English edition · Editorial review copy. '
                '<a href="'+url("review/")+'">Review status</a></div>') if review else ""
        robot='<meta name="robots" content="noindex,nofollow">' if review else '<meta name="robots" content="index,follow">'
        full='''<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>'''+e(title)+''' · estrategIA</title><meta name="description" content="'''+e(description)+'''">
'''+robot+'''<link rel="canonical" href="'''+e(canonical)+'''">
<meta property="og:type" content="'''+("article" if schema.get("@type")=="Article" else "website")+'''"><meta property="og:title" content="'''+e(title)+'''"><meta property="og:description" content="'''+e(description)+'''"><meta property="og:url" content="'''+e(canonical)+'''"><meta property="og:locale" content="en_GB"><meta name="twitter:card" content="summary">
<link rel="icon" href="'''+url("assets/favicon.svg")+'''" type="image/svg+xml">
<link rel="stylesheet" href="'''+url("assets/site.css")+'''"><script src="'''+url("assets/site.js")+'''" defer></script>
<link rel="alternate" type="application/atom+xml" title="estrategIA English edition" href="'''+url("feed.xml")+'''">
<script type="application/ld+json">'''+encoded+'''</script></head><body><a class="skip" href="#main">Skip to content</a>
'''+banner+'''<header class="wrap masthead"><div class="brand-block"><a class="brand" href="'''+url()+'''" aria-label="estrategIA home">estrateg<span>IA</span></a><span class="edition">English<br>edition</span></div><nav class="nav" aria-label="Main navigation">'''+navigation+'''<a class="spanish" href="https://estrategiabyaleph.substack.com">Read in Spanish</a></nav></header>
<main id="main" class="wrap">'''+body+'''</main>
<footer class="foot"><div class="wrap"><div class="foot-grid"><div><a class="brand" href="'''+url()+'''">estrateg<span>IA</span></a><p>Ideas about artificial intelligence, politics and government. From our Spanish archive, in English.</p></div><div><h2>Read</h2><ul><li><a href="'''+url("essays/")+'''">All essays</a></li><li><a href="'''+url("topics/")+'''">Explore topics</a></li><li><a href="https://estrategiabyaleph.substack.com/subscribe">Subscribe in Spanish</a></li></ul></div><div><h2>About this edition</h2><ul><li><a href="'''+url("about/")+'''">People and purpose</a></li><li><a href="'''+url("about/#translation-and-provenance")+'''">Translation and provenance</a></li><li><a href="'''+url("feed.xml")+'''">Follow new translations</a></li><li><a href="'''+url("catalog.json")+'''">Article catalogue</a></li></ul></div></div><div class="fineprint">© Institución Educativa ALEPH · Original publication dates are preserved. English translations retain the context of their Spanish originals.</div></div></footer></body></html>'''
        write(("index.html" if not route else route+"index.html"),full)
    def card(r,heading="h2"):
        t=r["topics"][0]
        search=" ".join([r["title"],r["description"],author_label(r),*r["topics"],plain(markdown.markdown(r["raw"]))])
        return '<article class="essay-card" data-essay data-search="'+e(search)+'" data-topics="'+e(" ".join(r["topics"]))+'" data-year="'+e((r.get("original_date") or "")[:4])+'"><div class="topic-label">'+e(TOPICS[t][0])+'</div><'+heading+'><a href="'+url(r["route"])+'">'+e(r["title"])+'</a></'+heading+'><p>'+e(r["description"])+'</p><div class="meta"><span>'+e(author_label(r))+'</span><span>'+date_label(r.get("original_date"))+'</span><span>'+str(r["minutes"])+' min read</span><span>Issue '+r["id"]+'</span></div></article>'
    records.sort(key=lambda r:r["issue_number"],reverse=True)
    lead=next((r for r in records if r["issue_number"]==155),records[0])
    featured='''<section class="feature" aria-labelledby="featured-title"><div><p class="eyebrow">Featured essay · Power and sovereignty</p><h2 id="featured-title"><a href="'''+url(lead["route"])+'''">'''+e(lead["title"])+'''</a></h2><p class="summary">'''+e(lead["description"])+'''</p><div class="meta"><span>'''+e(author_label(lead))+'''</span><span>'''+date_label(lead.get("original_date"))+'''</span><span>'''+str(lead["minutes"])+''' min read</span></div></div><aside class="feature-aside"><p class="eyebrow">Start here</p><h3>A different way into the AI debate.</h3><p>Who holds power? What can institutions do? How should the gains be shared? Follow the questions across our archive.</p><a class="text-link" href="'''+url("topics/")+'''">Explore the topics</a></aside></section>'''
    home='''<section class="intro"><div><p class="eyebrow">From the Spanish archive</p><h1>AI, politics<br>and government.</h1></div><div class="intro-copy"><p>estrategIA explores how artificial intelligence is changing public life: the power to decide, the work we do and the institutions we share.</p><p>This English edition brings the main essays from our Spanish-language publication to a wider conversation.</p><a class="text-link" href="'''+url("about/")+'''">Meet estrategIA</a></div></section>'''+featured
    start=[next(r for r in records if r["issue_number"]==n) for n in [131,132,104] if any(r["issue_number"]==n for r in records)]
    home+='<section><div class="section-heading"><h2>Three questions worth pursuing</h2><a href="'+url("essays/")+'">All '+str(len(records))+' essays</a></div><div class="essay-grid">'+"".join(card(r,"h3") for r in start)+'</div></section>'
    home+='<section><div class="section-heading"><h2>Explore the archive by idea</h2></div><div class="topics-list">'
    for slug,(name,desc) in TOPICS.items():
        count=sum(slug in r["topics"] for r in records)
        home+='<a class="topic-row" href="'+url("topics/"+slug+"/")+'"><strong>'+e(name)+'</strong><span>'+str(count)+(' essay' if count==1 else ' essays')+'</span></a>'
    home+='</div></section>'
    page("","AI, politics and government","The English edition of estrategIA: essays on artificial intelligence, public life and the power to decide.",home)
    years=sorted({r["original_date"][:4] for r in records if r.get("original_date")},reverse=True)
    filters='<form class="filters" role="search" onsubmit="return false"><label>Search the essays<input id="search" type="search" placeholder="An idea, a word, an author…" autocomplete="off"></label><label>Topic<select id="topic"><option value="">All topics</option>'+''.join('<option value="'+k+'">'+e(v[0])+'</option>' for k,v in TOPICS.items())+'</select></label><label>Original year<select id="year"><option value="">All years</option>'+''.join('<option>'+y+'</option>' for y in years)+'</select></label></form><noscript><p>All essays are listed below. Search and filters require JavaScript; reading does not.</p></noscript><p id="result-count" class="result-count" role="status" aria-live="polite">'+str(len(records))+' essays</p>'
    archive='<header class="page-heading"><p class="eyebrow">The English archive</p><h1>Essays</h1><p class="dek">Arguments, experiments and questions about AI in public life. Dates refer to the original Spanish editions.</p></header>'+filters+'<div class="essay-grid">'+"".join(card(r) for r in records)+'<p id="empty-results" class="empty" hidden>No essays match those filters. Try a different word or choose all topics.</p></div>'
    page("essays/","Essays","Browse and search the English essays from estrategIA.",archive,"Essays")
    topics='<header class="page-heading"><p class="eyebrow">Follow an idea</p><h1>Topics</h1><p class="dek">Seven ways into the public consequences of artificial intelligence.</p></header><div class="topics-list">'
    for slug,(name,desc) in TOPICS.items():
        selected=[r for r in records if slug in r["topics"]]
        topics+='<a class="topic-row" href="'+url("topics/"+slug+"/")+'"><strong>'+e(name)+'</strong><span>'+str(len(selected))+' essays</span></a>'
        inner='<header class="page-heading"><p class="eyebrow">A thread through the archive</p><h1>'+e(name)+'</h1><p class="dek">'+e(desc)+'</p></header>'
        inner+=('<div class="essay-grid">'+"".join(card(r) for r in selected)+'</div>') if selected else '<div class="empty"><p>Translations in this topic are being prepared. You can explore the complete original archive in Spanish.</p><a href="https://estrategiabyaleph.substack.com/archive">Read the Spanish archive</a></div>'
        page("topics/"+slug+"/",name,desc,inner,"Topics")
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
    about='<header class="page-heading"><p class="eyebrow">People, ideas and public life</p><h1>About estrategIA</h1></header><div class="about-layout"><div class="prose">'+markdown.markdown(about_md,extensions=["extra","toc"])+'</div><aside class="about-brand"><img src="'+url("assets/estrategia-header.png")+'" alt="The original estrategIA publication header" width="756" height="502"><p>An editorial initiative of Institución Educativa ALEPH.</p></aside></div>'
    page("about/","About estrategIA","The people, purpose and editorial method behind estrategIA's English edition.",about,"About")
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
        toc=converter.toc if converter.toc_tokens else ""
        genre=r.get("genre","analysis").replace("_"," ").title()
        byline=('<a href="'+e(r["author"].get("url") or config["original_site"])+'">'+e(author_name(r))+'</a>') if author_name(r) else e(author_label(r))
        headline='<div class="breadcrumbs"><a href="'+url("essays/")+'">Essays</a> / Issue '+r["id"]+'</div><header class="article-heading"><p class="eyebrow">'+e(TOPICS[r["topics"][0]][0])+' · '+e(genre)+'</p><h1>'+e(r["title"])+'</h1><p class="dek">'+e(r["description"])+'</p><div class="article-meta"><div><strong>'+byline+'</strong><span>Author</span></div><div><strong>'+date_label(r.get("original_date"))+'</strong><span>Originally published in Spanish</span></div><div><strong>'+str(r["minutes"])+' min read</strong><span>'+("English review draft" if review else "English edition · "+date_label(r["english_publication_date"]))+'</span></div></div></header>'
        historical='This is a translation of the original Spanish essay'+(' published on '+date_label(r["original_date"]) if r.get("original_date") else '')+'. Its claims, examples and forecasts retain that historical context.'
        citation=(author_name(r)+'. ' if author_name(r) else '')+'“'+r["title"]+'.” estrategIA, issue '+r["id"]+', '+date_label(r.get("original_date"))+'. English '+('translation, review draft' if review else 'edition, '+date_label(r["english_publication_date"]))+'. '+r["url"]
        body='<div class="article-body">'+rendered+'<div class="history-note">'+e(historical)+' <a href="'+e(r["original_url"])+'">Read the original Spanish edition</a>, including its accompanying illustrations.</div><section class="citation" aria-labelledby="cite-title"><h2 id="cite-title">Cite this essay</h2><p id="citation-text">'+e(citation)+'</p><button class="button" type="button" data-copy="citation-text">Copy citation</button><span class="status" role="status" aria-live="polite"></span></section></div>'
        aside='<aside class="article-aside" aria-label="Essay navigation"><h2>'+('In this essay' if toc else 'Read and cite')+'</h2>'+toc+'<div class="aside-links"><a href="'+e(r["original_url"])+'">Read in Spanish</a><a href="'+url("text/"+r["id"]+".md")+'">Read as Markdown</a><a href="#cite-title">Cite this essay</a></div></aside>'
        related=[x for x in records if x["id"]!=r["id"]]
        related.sort(key=lambda x:len(set(x["topics"])&set(r["topics"])),reverse=True)
        more='<section class="related"><div class="section-heading"><h2>Continue the conversation</h2></div><div class="essay-grid">'+"".join(card(x,"h3") for x in related[:3])+'</div></section>'
        schema={"@context":"https://schema.org","@type":"Article","@id":r["url"]+"#article","headline":r["title"],"description":r["description"],"inLanguage":"en-GB","url":r["url"],"publisher":{"@type":"Organization",**config["publisher"]},"genre":genre,"translationOfWork":{"@type":"Article","@id":r["original_url"],"url":r["original_url"],"inLanguage":"es"}}
        if author_name(r): schema["author"]={"@type":"Person","name":author_name(r),"url":r["author"].get("url") or r["original_url"]}
        if r.get("original_date"): schema["translationOfWork"]["datePublished"]=r["original_date"]
        if not review:
            schema["datePublished"]=r["english_publication_date"]
            if r.get("english_modified_date"):
                schema["dateModified"]=r["english_modified_date"]
        page(r["route"],r["title"],r["description"],headline+'<div class="article-layout">'+body+aside+'</div>'+more,"Essays",schema)
        export_header='# '+r["title"]+'\n\nAuthor: '+author_label(r)+'\nOriginal publication: '+str(r.get("original_date") or "unverified")+'\nSpanish original: '+r["original_url"]+'\nEnglish URL: '+r["url"]+'\nStatus: '+("Editorial review draft" if review else "Published translation")+'\n\n'+historical+'\n\n'
        if not review:
            export_header += "English publication: "+r["english_publication_date"]+"\n\n"
        # Absolute image URLs keep the plain-text copy portable.
        export_body=raw.replace(']('+prefix,']('+base)
        write("text/"+r["id"]+".md",export_header+export_body)
        catalogue.append({k:r.get(k) for k in ["id","issue_number","title","description","author","original_url","original_date","topics","genre","url"]}|{"inLanguage":"en-GB","markdown_url":base+"text/"+r["id"]+".md","english_publication_date":None if review else r["english_publication_date"],"english_modified_date":None if review else r.get("english_modified_date"),"status":"review_draft" if review else "published"})
    write("catalog.json",json.dumps({"title":config["title"],"status":"review_draft" if review else "published","articles":catalogue},ensure_ascii=False,indent=2))
    write("llms.txt","# estrategIA · English edition\n\n> Essays on AI, politics and government, translated from the Spanish publication.\n\n"+("This is an unpublished editorial review copy.\n\n" if review else "")+"Original dates and source links are retained. Historical analyses should not be read as current reporting.\n\n## Articles\n\n"+"".join("- ["+r["title"]+"]("+r["url"]+"): "+r["description"]+"\n" for r in records)+"\n## Resources\n\n- [Catalogue]("+base+"catalog.json)\n- [About]("+base+"about/)\n")
    routes=["","essays/","topics/","about/"]+["topics/"+x+"/" for x in TOPICS]+[r["route"] for r in records]
    sitemap=ET.Element("urlset",xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for route in ([] if review else routes):
        node=ET.SubElement(sitemap,"url"); ET.SubElement(node,"loc").text=base+route
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
        author=ET.SubElement(entry,"author"); ET.SubElement(author,"name").text=author_label(r)
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
    manifest["english_publication_dates"]={} if review else {r["id"]:r["english_publication_date"] for r in records}
    manifest["training_policy_verification"]=training_check
    write("build-manifest.json",json.dumps(manifest,indent=2))
    print(json.dumps({"output":str(output),"mode":args.mode,"articles":len(records),"files":len(manifest["files"])}))
if __name__=="__main__": main()
