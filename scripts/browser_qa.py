import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
base=json.loads((ROOT/"evidence/preview-server.json").read_text())["url"]
out=ROOT/"evidence/screenshots";out.mkdir(exist_ok=True)
result={"pages":[],"errors":[],"checks":[]}
with sync_playwright() as p:
    browser=p.chromium.launch(channel="msedge",headless=True)
    context=browser.new_context(viewport={"width":1440,"height":1000},device_scale_factor=1)
    page=context.new_page()
    page.on("pageerror",lambda error: result["errors"].append(str(error)))
    for route in ["","essays/","topics/","about/","essays/001/","essays/050/","essays/104/","essays/131/","essays/132/","essays/155/"]:
        response=page.goto(base+route);page.wait_for_load_state("networkidle")
        overflow=page.evaluate("document.documentElement.scrollWidth>innerWidth+1")
        broken=page.locator("img").evaluate_all("(imgs)=>imgs.filter(i=>!i.complete||i.naturalWidth===0).map(i=>i.src)")
        name=route.strip("/").replace("/","-") or "home"
        page.screenshot(path=str(out/(name+"-desktop.png")),full_page=True)
        result["pages"].append({"route":route,"width":1440,"status":response.status,"overflow":overflow,"broken_images":broken})
    page.goto(base+"essays/");page.locator("#search").fill("sovereignty")
    result["checks"].append({"name":"fulltext_search","passed":page.locator("[data-essay]:visible").count()>=1 and page.locator("[data-essay]:visible").count()<6})
    page.locator("#search").fill("qzxnonexistentterm")
    result["checks"].append({"name":"empty_state","passed":page.locator("#empty-results").is_visible() and page.locator("[data-essay]:visible").count()==0})
    page.locator("#search").fill("");page.locator("#year").select_option("2023")
    result["checks"].append({"name":"year_filter","passed":page.locator("[data-essay]:visible").count()==1})
    page.locator("#year").select_option("");page.locator("#topic").select_option("government")
    result["checks"].append({"name":"topic_filter","passed":page.locator("[data-essay]:visible").count()>=1})
    for width in [390,320]:
        page.set_viewport_size({"width":width,"height":844})
        for route in ["","essays/","about/","essays/104/","essays/155/"]:
            response=page.goto(base+route);page.wait_for_load_state("networkidle")
            overflow=page.evaluate("document.documentElement.scrollWidth>innerWidth+1")
            name=route.strip("/").replace("/","-") or "home"
            page.screenshot(path=str(out/(name+"-"+str(width)+".png")),full_page=True)
            result["pages"].append({"route":route,"width":width,"status":response.status,"overflow":overflow})
    page.set_viewport_size({"width":1280,"height":900});page.goto(base+"essays/155/")
    page.add_style_tag(content="html{font-size:200%}")
    result["checks"].append({"name":"text_200_percent","passed":not page.evaluate("document.documentElement.scrollWidth>innerWidth+1")})
    page.screenshot(path=str(out/"article-200-percent.png"),full_page=True)
    response=page.goto(base+"does-not-exist/")
    result["checks"].append({"name":"real_404","passed":response.status==404})
    context.close()
    nojs=browser.new_context(java_script_enabled=False,viewport={"width":390,"height":844})
    page=nojs.new_page();page.goto(base+"essays/155/")
    result["checks"].append({"name":"full_article_without_js","passed":len(page.locator(".article-body").inner_text())>8000 and page.locator("a[href$='text/155.md']").count()==1})
    page.goto(base+"essays/")
    result["checks"].append({"name":"archive_without_js","passed":page.locator("[data-essay]").count()==6})
    nojs.close();browser.close()
result["passed"]=not result["errors"] and all(r["status"]==200 and not r["overflow"] and not r.get("broken_images") for r in result["pages"]) and all(c["passed"] for c in result["checks"])
(ROOT/"evidence/QA_BROWSER.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result))
