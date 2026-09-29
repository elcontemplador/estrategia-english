from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
import xml.etree.ElementTree as ET
from people import load_profiles, profile_for, route as profile_route, author_entity, contributions, archive_profiles
from discovery import social_image
ROOT=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self): super().__init__();self.ids=set();self.links=[];self.images=[];self.h1=0;self.lang=None;self.canonical=[];self.robots=[];self.description=[];self.jsonld=[];self.capture=False;self.buf="";self.duplicates=[];self.meta={}
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="html":self.lang=a.get("lang")
        if tag=="h1":self.h1+=1
        if "id" in a:
            if a["id"] in self.ids:self.duplicates.append(a["id"])
            self.ids.add(a["id"])
        if tag=="a" and "href" in a:self.links.append(a["href"])
        if tag in ["script","link","img"]:
            value=a.get("src") if tag!="link" else a.get("href")
            if value:self.links.append(value)
        if tag=="img":self.images.append(a)
        if tag=="link" and a.get("rel")=="canonical":self.canonical.append(a.get("href"))
        if tag=="meta" and a.get("name")=="robots":self.robots.append(a.get("content",""))
        if tag=="meta" and a.get("name")=="description":self.description.append(a.get("content",""))
        if tag=="meta":self.meta.setdefault(a.get("property") or a.get("name"),[]).append(a.get("content",""))
        if tag=="script" and a.get("type")=="application/ld+json":self.capture=True;self.buf=""
    def handle_data(self,data):
        if self.capture:self.buf+=data
    def handle_endtag(self,tag):
        if tag=="script" and self.capture:self.jsonld.append(json.loads(self.buf));self.capture=False
def run(folder):
    profiles=load_profiles(ROOT)
    base=ROOT/folder;manifest=json.loads((base/"build-manifest.json").read_text())
    prefix=urlsplit(manifest["base_url"]).path.rstrip("/")+"/"
    errors=[];checks=0;pages={}
    def check(condition,message):
        nonlocal checks
        checks+=1
        if not condition:errors.append(message)
    for path in base.rglob("*.html"):
        p=Page();text=path.read_text(encoding="utf-8");p.feed(text);pages[path.resolve()]=p
        check(p.h1==1,f"{path}: h1 count {p.h1}")
        check(p.lang=="en-GB",f"{path}: language")
        check(len(p.canonical)==1,f"{path}: canonical")
        check(bool(p.description and p.description[0]),f"{path}: description")
        check(not p.duplicates,f"{path}: duplicate IDs {p.duplicates}")
        check(bool(p.jsonld),f"{path}: JSON-LD")
        check(not re.search(r"(?:D:|C:)\\|D:/estrategia|C:/Users",text),f"{path}: local path leak")
        check("Date being verified" not in text,f"{path}: date pending")
        check(all(img.get("alt","").strip() for img in p.images),f"{path}: image alt missing")
        is_error=path.relative_to(base).as_posix() in ("404.html","404/index.html")
        check(("noindex" in ",".join(p.robots))==(manifest["mode"]=="review" or is_error),f"{path}: robots mode")
        check(p.meta.get("og:url")==p.canonical,f"{path}: social URL matches canonical")
        article=next((s for s in p.jsonld if s.get('@type')=='Article'),{})
        image=social_image(article.get('image',[])) or {}
        check(p.meta.get("og:image")==[image.get('url') or manifest["base_url"]+"assets/estrategia-header.png"],f"{path}: absolute social image matches article or brand fallback")
        check(p.meta.get('twitter:image')==p.meta.get('og:image'),f'{path}: consistent social previews')
        check(bool(p.meta.get("og:image:alt",[""])[0]),f"{path}: social image description")
        check(p.meta.get("twitter:card")==["summary_large_image"],f"{path}: social card")
        for img in p.images:
            if img.get("src") and "assets/images/" in img["src"]:
                check(all(str(img.get(k,"")).isdigit() and int(img[k])>0 for k in ("width","height")),f"{path}: image dimensions {img['src']}")
                check(img.get("loading")=="lazy" and img.get("decoding")=="async",f"{path}: deferred image loading")
        for schema in p.jsonld:
            if schema.get("@type")=="CollectionPage":
                items=schema["mainEntity"]["itemListElement"]
                check(schema["mainEntity"]["numberOfItems"]==len(items),f"{path}: collection count")
                check(all(urlsplit(item["url"]).path in p.links for item in items),f"{path}: collection matches visible links")
            elif schema.get("@type")=="BreadcrumbList":
                check(schema["itemListElement"][-1]["item"]==p.canonical[0],f"{path}: breadcrumb canonical")
    for path,p in pages.items():
        for link in p.links:
            parsed=urlsplit(link)
            if parsed.scheme or parsed.netloc:continue
            check(not parsed.path or parsed.path.startswith(prefix),f"{path}: bad local URL {link}")
            if not parsed.path:target=path
            else:
                target=(base/unquote(parsed.path.removeprefix(prefix))).resolve()
                if parsed.path.endswith("/"):target=target/"index.html"
            check(target.is_file(),f"{path}: missing target {link}")
            if parsed.fragment and target in pages:check(unquote(parsed.fragment) in pages[target].ids,f"{path}: missing anchor {link}")
    catalog=json.loads((base/"catalog.json").read_text(encoding="utf-8"))
    profiles=archive_profiles(profiles,catalog['articles'])
    people_export=json.loads((base/'people.json').read_text(encoding='utf-8'))['people']
    check([(p['name'],p['group']) for p in people_export]==[(p['name'],p['group']) for p in profiles], 'People export includes every guest and editorial profile in order')
    directory=(base/'people/index.html').read_text(encoding='utf-8')
    for profile in profiles:
        check(prefix+profile_route(profile) in directory,profile['slug']+': listed in people directory')
    check(len(catalog["articles"])==manifest["article_count"],"Catalogue count")
    for r in catalog["articles"]:
        check(bool(r["original_date"] and r["original_url"]),r["id"]+": missing provenance")
        p=base/"essays"/r["id"]/"index.html"
        data=pages[p.resolve()].jsonld[0]
        expected_author=(r.get("author") or {}).get("name")
        if r.get("authors"):
            expected=[author_entity(a,profiles,manifest['base_url']) for a in r['authors']]
            check(data.get("author")==expected,r["id"]+": all structured coauthors match source metadata in order")
            source_meta=json.loads((ROOT/"content/en"/(r["id"]+".json")).read_text(encoding="utf-8-sig"))
            check(r["authors"]==source_meta.get("authors"),r["id"]+": catalogue retains original coauthor records")
            for a in r['authors']:
                profile=profile_for(a,profiles)
                href=prefix+profile_route(profile) if profile else a.get('url')
                check(not href or href in pages[p.resolve()].links,r['id']+': coauthor profile link is present')
        else:
            check((data.get("author") or {}).get("name")==expected_author,r["id"]+": schema author matches source metadata")
            if expected_author: check(data["author"].get("@type")==r["author"].get("type","Person"),r["id"]+": author entity type matches metadata")
            if expected_author:
                check(data['author']==author_entity(r['author'],profiles,manifest['base_url']),r['id']+': author identity and URL match registry')
                profile=profile_for(r['author'],profiles)
                if profile: check(prefix+profile_route(profile) in pages[p.resolve()].links,r['id']+': internal author link present')
        if not expected_author:
            html_text=p.read_text(encoding="utf-8")
            check("Byline not stated in original" in html_text,r["id"]+": missing visible unknown-byline notice")
            check("author" not in data,r["id"]+": invented structured author")
        check(data["translationOfWork"].get("datePublished")==r["original_date"],r["id"]+": original schema date")
        check((data.get("datePublished") is None)==(manifest["mode"]=="review"),r["id"]+": English schema date")
        check(data.get("mainEntityOfPage",{}).get("@id")==r["url"],r["id"]+": main entity canonical")
        check(data.get("isPartOf",{}).get("@type")=="Periodical",r["id"]+": publication identity")
        check(data.get('isAccessibleForFree') is True,r['id']+': free access stated')
        check(data.get('encoding',{}).get('contentUrl')==r['markdown_url'],r['id']+': Markdown representation matches catalogue')
        visible_images={urlsplit(i['src']).path for i in pages[p.resolve()].images if i.get('src')}
        check(all(urlsplit(i['url']).path in visible_images for i in data.get('image',[])),r['id']+': structured images appear in article')
        check(isinstance(data.get("wordCount"),int) and data["wordCount"]>0,r["id"]+": readable word count")
        md=(base/"text"/(r["id"]+".md")).read_text(encoding="utf-8")
        check(r["title"] in md and r["original_url"] in md,r["id"]+": Markdown provenance")
        check(not re.search(r"\]\((?:assets|D:|C:)",md),r["id"]+": Markdown relative asset")
    for profile in profiles:
        page_path=(base/profile_route(profile)/'index.html').resolve()
        check(page_path in pages,profile['slug']+': profile page exists')
        if page_path not in pages: continue
        data=pages[page_path].jsonld[0]
        expected_url=manifest['base_url']+profile_route(profile)
        check(data.get('@type')=='ProfilePage' and data.get('mainEntity',{}).get('@id')==expected_url+'#person',profile['slug']+': canonical person identity')
        check(data['mainEntity'].get('name')==profile['name'],profile['slug']+': visible and structured name')
        selected=contributions(profile,catalog['articles'])
        expected_urls=[r['url'] for r in selected]
        check([r['url'] for r in data.get('hasPart',[])]==expected_urls,profile['slug']+': exact authored essay coverage')
        check(all(urlsplit(href).path in pages[page_path].links for href in expected_urls),profile['slug']+': authored essays visible')
        check(all(link['url'] in pages[page_path].links for link in profile['links']),profile['slug']+': external biography links present')
    for f in ["feed.xml","sitemap.xml"]:ET.parse(base/f);check(True,f+": XML parse")
    search=json.loads((base/"search-index.json").read_text(encoding="utf-8"))["articles"]
    check([a["id"] for a in search]==[a["id"] for a in catalog["articles"]],"Search index covers catalogue in order")
    check(all(a.get("text","").strip() for a in search),"Search index contains text")
    check((base/"robots.txt").read_text().startswith("#"),"robots is text")
    result={"mode":manifest["mode"],"checks":checks,"html_pages":len(pages),"articles":len(catalog["articles"]),"passed":not errors,"errors":errors}
    evidence=ROOT/"evidence"/("QA_"+folder.upper()+".json")
    evidence.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
    return 0 if not errors else 1
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--root",choices=["preview","dist"],default="preview")
    sys.exit(run(ap.parse_args().root))
