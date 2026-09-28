"""Reproducible inventory. Public API reads and derivatives only; no external AI calls.
Run: python -B scripts/inventory.py [--refresh-public-metadata]
"""
from __future__ import annotations
import argparse, hashlib, html, importlib.util, json, re, sys, urllib.parse, urllib.request
from html.parser import HTMLParser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
PARENT=PROJECT.parent
CORPUS=PARENT/"corpus"/"issues"
DATA=PROJECT/"data"
EVIDENCE=PROJECT/"evidence"
SOURCES=EVIDENCE/"sources"
SPANISH=PROJECT/"content"/"es"
BASE="https://estrategiabyaleph.substack.com"
PILOTS=(1,50,104,131,132,155)
PILOT_LIMITS={1:(1,43),50:(1,43),104:(3,90),131:(1,61),132:(9,67),155:(9,79)}
NAMES=["Fernando Nieto Lobato","Pilar Mairal Medina","Fernando Domínguez Sardou","Roxana Mazzola","Pep Martorell","Pablo Martín","Harvey Sánchez-Restrepo","Sofía García Morales","Sofía García","Román Robles Valades","Juan Segundo Hevia","Pablo Martín Fernández"]
GUESTS={31:"Pilar Mairal Medina",58:"Fernando Domínguez Sardou",99:"Pep Martorell",104:"Roxana Mazzola",114:"Pablo Martín",122:"Harvey Sánchez-Restrepo",129:"Sofía García",134:"Román Robles Valades",139:"Juan Segundo Hevia"}
NAMES += ["Pablo Martín Diez","Santiago Comadira","Gustavo Fedi","Fernando Ujaldón","Ray Acosta","Javier Naranjo Sanjuan","Carlos Guadián","César Batiz","Martín Sosa Dirié","Mauricio Pilleux","Gabriela Ortega Jarrín","Alejandro Ulloa García","Josep M. (Pep) Martorell","Ignacio Martín Granados","Luis Eduardo Paniagua Martín","Javier Battilana Urbieta","Carlos López Ariztegui","El equipo de estrategIA"]
GUESTS.update({19:"Santiago Comadira",22:"Gustavo Fedi",26:"Fernando Ujaldón",35:"Ray Acosta",54:"Javier Naranjo Sanjuan",60:"Carlos Guadián",62:"César Batiz",67:"Martín Sosa Dirié",78:"Martín Sosa Dirié",84:"Mauricio Pilleux",88:"Gabriela Ortega Jarrín",92:"Alejandro Ulloa García",99:"Josep M. (Pep) Martorell",102:"Ignacio Martín Granados",106:"Ignacio Martín Granados",109:"Luis Eduardo Paniagua Martín",112:"Javier Battilana Urbieta",114:"Pablo Martín Diez",126:"Carlos López Ariztegui"})
BOUNDARY_CORRECTIONS={30:(28,300),54:(9,65),126:(7,53)}
FICTION=set(range(41,48))|set(range(93,98))|set(range(144,152))
GREETINGS={13,65,117}
BOUNDARY=re.compile(r"^(?:#{1,6}\s*)?(?:\*\*|_)*(?:Actualidad y art[ií]culos|IA en acci[oó]n|Comparta estrategIA|Difunda estrategIA|Comparta nuestra|Herramienta de IA de la semana)",re.I)
PROMO=re.compile(r"^Gracias por leer estrategIA\s*!.*Suscr",re.I)
ISSUE=re.compile(r"\.estrategia-(\d+)(?:-|\.md)",re.I)
IMAGE=re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
ERRORS=[]
OFFLINE=True

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; estrategIA-editorial-inventory/1.0)"})
    with urllib.request.urlopen(req,timeout=35) as r: return json.loads(r.read().decode("utf-8"))

def clean(text):
    text=re.sub(r"!\[([^\]]*)\]\([^\n]*?\)",r"\1",text)
    text=re.sub(r"\[([^\]]+)\]\([^\n]*?\)",r"\1",text)
    return re.sub(r"\s+"," ",re.sub(r"[*_\x60#]","",text)).strip()

def minimum(post):
    return {k:post.get(k) for k in ("id","slug","title","subtitle","post_date","canonical_url","updated_at","is_published") if post.get(k) is not None}

def public_data(refresh):
    cache=SOURCES/"substack_public_metadata.json"
    if cache.exists() and not refresh: return json.loads(cache.read_text(encoding="utf-8"))
    if OFFLINE:
        return {"source":"offline_local_sources_only","items":[],"requests":[],"errors":[]}
    archive=[]; requests=[]
    for offset in range(0,400,20):
        url=BASE+"/api/v1/archive?"+urllib.parse.urlencode({"sort":"new","limit":20,"offset":offset})
        try:
            page=fetch(url)
            if not isinstance(page,list): raise ValueError("Non-list archive response")
        except Exception as error:
            ERRORS.append({"url":url,"error":str(error)}); break
        archive.extend(minimum(x) for x in page)
        requests.append({"url":url,"count":len(page)})
        if len(page)<20: break
    result={"retrieved_at":datetime.now(timezone.utc).isoformat(),"source":"Substack public read-only API","requests":requests,"items":archive,"errors":list(ERRORS)}
    if archive: write_json(cache,result)
    return result

def save_post(slug,refresh=False):
    meta_path=SOURCES/(slug+".json"); html_path=SOURCES/(slug+".html")
    if meta_path.exists() and html_path.exists() and not refresh:
        return json.loads(meta_path.read_text(encoding="utf-8")),html_path
    if OFFLINE: return None,None
    url=BASE+"/api/v1/posts/"+slug
    try:
        post=fetch(url); raw=post.get("body_html","")
        if not raw: raise ValueError("No public body_html")
        html_path.write_text(raw,encoding="utf-8",newline="\n")
        meta=minimum(post)
        meta.update({"api_url":url,"retrieved_at":datetime.now(timezone.utc).isoformat(),"body_html_file":str(html_path),"body_html_sha256":digest(html_path)})
        write_json(meta_path,meta); return meta,html_path
    except Exception as error:
        ERRORS.append({"url":url,"error":str(error)}); return None,None

def source156(public,refresh):
    match=next((x for x in public["items"] if x["slug"].startswith("estrategia-156-")),None)
    slug=match["slug"] if match else "estrategia-156-como-hacer-segura"
    meta,html=save_post(slug,refresh)
    if not meta: return None
    spec=importlib.util.spec_from_file_location("source_converter",PARENT/"scripts"/"download_substack_issues.py")
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    path=SOURCES/(str(meta["id"])+"."+slug+".md")
    path.write_text(module.render_post({**meta,"body_html":html.read_text(encoding="utf-8")}),encoding="utf-8",newline="\n")
    return path

def bounds(n,lines):
    if n in PILOT_LIMITS: return *PILOT_LIMITS[n],"reviewed_source_boundaries"
    if n in BOUNDARY_CORRECTIONS: return *BOUNDARY_CORRECTIONS[n],"preliminary_boundaries_corrected_after_diagnostic"
    if not any(x.strip() for x in lines): return None,None,"excluded_empty_auxiliary"
    start=9 if any(x.startswith("Publicado:") for x in lines[:8]) else 1
    end=len(lines)
    for i,line in enumerate(lines,1):
        if i>=start and BOUNDARY.match(line.strip()): end=i-1; break
    while end>=start and (not lines[end-1].strip() or lines[end-1].strip()=="---"): end-=1
    return start,end,"preliminary_requires_editorial_review"

def title(n,lines,start,end):
    if n==132: return "La IA no nos quita el trabajo: nos libera de él"
    for line in lines[start-1:min(end,start+20)]:
        if re.match(r"^#{1,6}\s",line) and not clean(line).lower().startswith("newsletter pionera"): return clean(line)
    return None

def byline(n,lines,start,end):
    found=[]
    for pos,line in enumerate(lines[start-1:end],start):
        for name in NAMES:
            if clean(line).strip(" []>.,").casefold()==name.casefold():
                url=re.search(r"\[[^\]]+\]\((https?://[^)]+)\)","".join(lines[pos-1:min(pos+3,end)]))
                found.append({"name":name,"url":url[1] if url else None,"evidence_line":pos,"status":"explicit_article_byline"})
    if n==130:
        group=[]
        for pos,line in enumerate(lines[:end],1):
            if pos in (101,103,105,107,109,111,113,115):
                m=re.match(r"\[([^\]]+)\]\(([^)]+)\)",line)
                if m: group.append({"name":m[1],"url":m[2],"evidence_line":pos,"status":"explicit_article_coauthor_byline"})
        if len(group)==8:
            return {"name":"; ".join(x["name"] for x in group),"url":None,"evidence_line":101,"status":"explicit_eight_article_coauthors"},group
    if found: return next((x for x in found if GUESTS.get(n) and x["name"].startswith(GUESTS[n])),None) or found[-1],found
    guest=GUESTS.get(n)
    if guest:
        for pos,line in enumerate(lines[:end],1):
            if guest in line:
                url=re.search(r"\["+re.escape(guest)+r"[^\]]*\]\((https?://[^)]+)\)",line)
                return {"name":guest,"url":url[1] if url else None,"evidence_line":pos,"status":"explicit_editorial_attribution"},[]
    return None,[]

def genre(n):
    if n is None: return "auxiliary"
    if n==0: return "welcome"
    if n in FICTION: return "fiction"
    if n in GREETINGS: return "editorial_greeting"
    if n in {27,39,48,53,100,105,118,152}: return "retrospective"
    if n in {2,34,38,40,71,77,81,90,108,123,140,153}: return "review_or_commentary"
    if n in {3,9,15,16,17,23,24,25,28,29,30,36,50,60,64,75,80,86,101,110,115,128,135,136,141,143}: return "practical_experiment"
    return "analysis"

def extract(n,lines,start,end,heading):
    kept=[]; removed=[]
    for pos,line in enumerate(lines[start-1:end],start):
        if PROMO.match(line.strip()): removed.append(pos)
        else: kept.append(line)
    if n==132: kept=["# "+heading,""]+[x for x in kept if clean(x)!=heading]
    else:
        first=next((i for i,x in enumerate(kept) if x.startswith("#")),None)
        if first is not None: kept[first]="# "+heading
        else: kept=["# "+(heading or "Untitled source"),""]+kept
    text="\n".join(kept).strip()+"\n"
    def remap(m):
        alt,target=m.groups()
        if target.startswith("estrategIA_MD/Attachments/"): return f"![{alt}]({(CORPUS/'Attachments'/target.split('/')[-1]).as_posix()})"
        return m[0]
    return IMAGE.sub(remap,text),removed

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts=[]
    def handle_data(self,text): self.parts.append(text)
    def handle_starttag(self,tag,attrs):
        if tag in {"p","div","li","h1","h2","h3","h4","br","blockquote"}: self.parts.append(" ")
    def handle_endtag(self,tag):
        if tag in {"p","div","li","h1","h2","h3","h4","br","blockquote"}: self.parts.append(" ")

def comparison_normalize(text):
    text=re.sub(r"!\[[^\]]*\]\([^\n]+\)"," ",text)
    text=re.sub(r"\[([^\]]+)\]\([^\n]*?\)",r"\1",text)
    text=re.sub(r"https?://[^\s)]+"," ",text)
    return re.sub(r"[\W_]","",html.unescape(text).lower())

def source_comparison(items):
    reports=[]
    for item in items:
        if item["issue_number"] not in PILOTS: continue
        snapshot=item.get("public_snapshot")
        if not snapshot:
            reports.append({"issue_number":item["issue_number"],"status":"pending_public_snapshot"})
            continue
        parser=VisibleText()
        parser.feed(Path(snapshot["html_file"]).read_text(encoding="utf-8"))
        published=comparison_normalize("".join(parser.parts))
        text=Path(item["extracted_file"]).read_text(encoding="utf-8")
        blocks=[(i,comparison_normalize(x)) for i,x in enumerate(re.split(r"\n\s*\n",text)) if len(comparison_normalize(x))>150]
        missing=[i for i,block in blocks if block not in published]
        reports.append({"issue_number":item["issue_number"],"checked_substantial_blocks":len(blocks),"unmatched_block_indices":missing,"status":"pass_normalized_substantial_text" if not missing else "requires_comparison","source_sha256":item["source_sha256"],"extracted_sha256":item["extracted_sha256"],"published_html_sha256":snapshot["html_sha256"]})
    write_json(EVIDENCE/"INVENTORY_PILOT_SOURCE_QA.json",{"method":"Every source block longer than 150 normalized characters must occur in public HTML visible text. Ignore punctuation, case, whitespace and Markdown, preserving letters and digits.","limitations":["This corroborates substantial text against publication, not semantic translation accuracy.","Short blocks, source links, images and punctuation need separate checks.","No human approval is asserted."],"reports":reports})

def build(refresh=False):
    for path in (DATA,EVIDENCE,SOURCES,SPANISH): path.mkdir(parents=True,exist_ok=True)
    protected=list(CORPUS.glob("*.md"))+list((PARENT/"corpus"/"canon_estilo").glob("*.md"))+[PARENT/"data"/"estrategia_index.sqlite",PARENT/"data"/"temas_historicos.csv"]
    before={str(p):digest(p) for p in protected}
    public=public_data(refresh); byslug={x["slug"]:x for x in public["items"]}
    extra=source156(public,refresh)
    paths=list(CORPUS.glob("*.md"))+([extra] if extra else [])
    items=[]
    for path in paths:
        lines=path.read_text(encoding="utf-8-sig").splitlines()
        m=ISSUE.search(path.name); n=int(m[1]) if m else (0 if "bienvenidos-a-estrategia" in path.name else None)
        slug=path.stem.split(".",1)[-1]; posted=byslug.get(slug); start,end,status=bounds(n,lines)
        if not posted:
            explicit_date=next((re.search(r"^Publicado:\s*(\d{4}-\d{2}-\d{2})",x) for x in lines[:8] if x.startswith("Publicado:")),None)
            explicit_url=next((x.removeprefix("URL:").strip() for x in lines[:8] if x.startswith("URL:")),None)
            if explicit_date:
                posted={"post_date":explicit_date[1],"canonical_url":explicit_url,"title":clean(lines[0]),"date_status":"verified_local_publication_header"}
            elif n==1:
                posted={"post_date":"2023-10-04","canonical_url":BASE+"/p/estrategia-1","title":None,"date_status":"verified_retrospective_corpus_issue27_line3"}
        item={"issue_number":n,"title":None,"newsletter_title":posted.get("title") if posted else None,"source_file":str(path),"source_sha256":digest(path),"original_url":posted.get("canonical_url") if posted else None,"original_date":posted.get("post_date","").split("T")[0] if posted else None,"original_timestamp":posted.get("post_date") if posted else None,"date_status":posted.get("date_status","verified_public_substack_api") if posted else "unverified","author":None,"genre":genre(n),"genre_status":"editorially_classified_for_pilot" if n in PILOTS else "preliminary_classification","main_start_line":start,"main_end_line":end,"main_word_count":0,"extraction_status":status,"notes":[]}
        item["url_status"]="verified_public_substack_api" if posted and posted.get("date_status","verified_public_substack_api")=="verified_public_substack_api" else "pending"
        if not item["original_url"] and n is not None:
            source_text="\n".join(lines)
            observed=BASE+"/p/"+slug
            open_form="https://open.substack.com/pub/estrategiabyaleph/p/"+slug
            if observed in source_text or open_form in source_text:
                item["original_url"]=observed
                item["url_status"]="verified_self_link_in_source"
            else:
                item["original_url"]=observed
                item["url_status"]="derived_from_source_filename_pending_live_check"
        if item["original_url"] and item["url_status"]=="pending":
            item["url_status"]="documented_in_local_source"
        if start is not None:
            heading=title(n,lines,start,end)
            if not heading:
                heading=clean(posted.get("title","")) if posted else None
                item["notes"].append("No autonomous article heading detected; newsletter title used provisionally where available.")
            item["title"]=heading
            author,candidates=byline(n,lines,start,end); item["author"]=author; item["author_candidates"]=candidates
            item["authors"]=candidates if n==130 else ([author] if author else [])
            item["title_status"]="reviewed_article_title" if n in PILOTS else "preliminary_article_title"
            text,removed=extract(n,lines,start,end,heading); stem=f"{n:03d}" if n is not None else path.stem
            derived=SPANISH/(stem+".md"); derived.write_text(text,encoding="utf-8",newline="\n")
            item.update({"extracted_file":str(derived),"extracted_sha256":digest(derived),"main_word_count":len(re.findall(r"\b\w+\b",clean(text))),"removed_promotion_lines":removed})
            assets=[]
            for alt,target in IMAGE.findall(text):
                a={"source":target,"alt":alt,"kind":"remote" if target.startswith(("https://","http://")) else "local"}
                if a["kind"]=="local": a.update({"exists":Path(target).exists(),"sha256":digest(Path(target)) if Path(target).exists() else None})
                assets.append(a)
            item["images"]=assets
            if n in BOUNDARY_CORRECTIONS: item["notes"].append("Diagnostic correction removes a distinct event or survey promotion; remaining boundaries remain provisional.")
            if n not in PILOTS: item["notes"].append("Automatic extraction is provisional; not a reviewed publication source.")
            if not author: item["notes"].append("Article authorship requires manual attribution; publication account is not treated as article author.")
            if n in FICTION: item["notes"].append("Fiction: preserve original AI-creation attribution and commentary after fiction; narrative credit still requires review.")
            if n in GREETINGS: item["notes"].append("Short editorial greeting, not a conventional essay; presentation requires classification.")
            if not any(BOUNDARY.match(x.strip()) for x in lines): item["notes"].append("No standard section boundary detected; whole-source candidate requires manual review.")
            if n==104: item["notes"].extend(["Guest translation/republication rights pending confirmation.","Newsletter introduction excluded; author biography, contact, bibliography and two substantive infographics retained."])
            if n==132: item["notes"].append("Substantive prefatory note preserved below article title; only title/note order changed.")
            if n==1: item["notes"].append("Quotes translated from English in Spanish source: verify original English wording or label a retranslation.")
            if n in PILOTS:
                meta,html=save_post(slug,refresh)
                if meta:
                    item["public_snapshot"]={"html_file":str(html),"html_sha256":digest(html),"metadata_file":str(SOURCES/(slug+".json"))}
                    item["notes"].append("Public HTML retained for source comparison; snapshot alone is not full-text equivalence verification.")
            item["rights_status"]="pending_contributor_translation_permission_check" if author and author["name"] not in {"Fernando Nieto Lobato","Pablo Martín Diez","Pablo Martín","El equipo de estrategIA"} else "editorial_owner_acceptance_pending"
        else:
            item["notes"].append("Empty auxiliary file, excluded from article corpus."); item["rights_status"]="not_applicable"
        items.append(item)
    if 156 not in [x["issue_number"] for x in items]:
        items.append({"issue_number":156,"title":"Cómo hacer segura la IA sin entregar su futuro a unos pocos","newsletter_title":None,"source_file":None,"source_sha256":None,"original_url":BASE+"/p/estrategia-156-como-hacer-segura","original_date":"2026-09-23","original_timestamp":None,"date_status":"documented_prior_editorial_verification_not_retrieved","author":None,"genre":"analysis","genre_status":"preliminary_classification","main_start_line":None,"main_end_line":None,"main_word_count":0,"extraction_status":"pending_published_source_retrieval","notes":["Published edition referenced in parent anniversary evidence; local V7 is not equivalent. Public retrieval blocked by approval reviewer in this run; no bypass attempted."],"rights_status":"editorial_owner_acceptance_pending"})
    items.sort(key=lambda x:(x["issue_number"] is None,x["issue_number"] if x["issue_number"] is not None else 999))
    numbers={x["issue_number"] for x in items}; substantive=[x for x in items if x["main_start_line"] is not None]
    summary={"generated_at":datetime.now(timezone.utc).isoformat(),"source_markdown_count":len(paths),"catalog_entry_count":len(items),"published_source_pending":sum(x["extraction_status"]=="pending_published_source_retrieval" for x in items),"numbered_sources_available":len([x for x in items if x["issue_number"] and x["main_start_line"] is not None]),"numbered_issues":len([x for x in items if x["issue_number"] and x["issue_number"]>0]),"numbered_range":[1,max(x for x in numbers if x is not None)],"missing_numbers_1_to_156":sorted(set(range(1,157))-numbers),"welcome_count":sum(x["issue_number"]==0 for x in items),"empty_auxiliary_count":sum(x["extraction_status"]=="excluded_empty_auxiliary" for x in items),"substantive_source_count":len(substantive),"dates_verified_public_api":sum(x["date_status"]=="verified_public_substack_api" for x in items),"authorship_accredited":sum(x["author"] is not None for x in substantive),"authorship_pending":sum(x["author"] is None for x in substantive),"reviewed_pilot_boundaries":sum(x["extraction_status"]=="reviewed_source_boundaries" for x in items),"preliminary_boundaries":sum(x["extraction_status"].startswith("preliminary") for x in items),"preliminary_words":sum(x["main_word_count"] for x in substantive),"genre_counts":dict(Counter(x["genre"] for x in items)),"network_errors":list(ERRORS),"publication_status":"not_published","human_approval":"pending"}
    result={"schema_version":1,"summary":summary,"items":items}
    write_json(DATA/"inventory.json",result)
    write_json(DATA/"pilot_sources.json",{"schema_version":1,"source":"inventory.json","items":[x for x in items if x["issue_number"] in PILOTS],"notes":["Six source boundaries reviewed; translation, independent semantic comparison and human acceptance are separate.","Date status is explicit per source: public API when available; otherwise local publication header, retrospective evidence, or null. Never weekly cadence."]})
    after={str(p):digest(p) for p in protected}; changed=[p for p in before if before[p]!=after[p]]
    write_json(EVIDENCE/"INVENTORY_INTEGRITY.json",{"checked_at":datetime.now(timezone.utc).isoformat(),"protected_file_count":len(before),"unchanged":not changed,"changed_files":changed,"sha256_before":before,"sha256_after":after})
    sample={0,1,13,30,41,50,54,65,66,70,93,104,117,118,126,131,132,144,155,156}
    write_json(EVIDENCE/"INVENTORY_DIAGNOSTICS.json",{"missing_numbers":summary["missing_numbers_1_to_156"],"pending_authorship":[{"issue_number":x["issue_number"],"title":x["title"]} for x in substantive if not x["author"]],"special_cases":[{"issue_number":x["issue_number"],"genre":x["genre"],"notes":x["notes"]} for x in items if x["genre"] in {"fiction","welcome","editorial_greeting","auxiliary"}],"boundary_sample":[{k:x[k] for k in ("issue_number","title","main_start_line","main_end_line","main_word_count","extraction_status")} for x in items if x["issue_number"] in sample]})
    source_comparison(items)
    if changed: raise RuntimeError("Protected source changed during inventory")
    print(json.dumps(summary,ensure_ascii=False,indent=2)); print("PILOT_SOURCES_READY",str(DATA/"pilot_sources.json"))
    return result

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-public-metadata",action="store_true")
    parser.add_argument("--offline",action="store_true",help="Only local files, no HTTP requests")
    args=parser.parse_args()
    OFFLINE=args.offline or not args.refresh_public_metadata
    build(args.refresh_public_metadata)
