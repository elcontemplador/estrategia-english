from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self): super().__init__();self.ids=set();self.links=[];self.images=[];self.h1=0;self.lang=None;self.canonical=[];self.robots=[];self.description=[];self.jsonld=[];self.capture=False;self.buf="";self.duplicates=[]
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
        if tag=="script" and a.get("type")=="application/ld+json":self.capture=True;self.buf=""
    def handle_data(self,data):
        if self.capture:self.buf+=data
    def handle_endtag(self,tag):
        if tag=="script" and self.capture:self.jsonld.append(json.loads(self.buf));self.capture=False
def run(folder):
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
        check(("noindex" in ",".join(p.robots))==(manifest["mode"]=="review"),f"{path}: robots mode")
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
    check(len(catalog["articles"])==manifest["article_count"],"Catalogue count")
    for r in catalog["articles"]:
        check(bool(r["original_date"] and r["original_url"]),r["id"]+": missing provenance")
        p=base/"essays"/r["id"]/"index.html"
        data=pages[p.resolve()].jsonld[0]
        check(data["translationOfWork"].get("datePublished")==r["original_date"],r["id"]+": original schema date")
        check((data.get("datePublished") is None)==(manifest["mode"]=="review"),r["id"]+": English schema date")
        md=(base/"text"/(r["id"]+".md")).read_text(encoding="utf-8")
        check(r["title"] in md and r["original_url"] in md,r["id"]+": Markdown provenance")
        check(not re.search(r"\]\((?:assets|D:|C:)",md),r["id"]+": Markdown relative asset")
    for f in ["feed.xml","sitemap.xml"]:ET.parse(base/f);check(True,f+": XML parse")
    check((base/"robots.txt").read_text().startswith("#"),"robots is text")
    result={"mode":manifest["mode"],"checks":checks,"html_pages":len(pages),"articles":len(catalog["articles"]),"passed":not errors,"errors":errors}
    evidence=ROOT/"evidence"/("QA_"+folder.upper()+".json")
    evidence.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
    return 0 if not errors else 1
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--root",choices=["preview","dist"],default="preview")
    sys.exit(run(ap.parse_args().root))
