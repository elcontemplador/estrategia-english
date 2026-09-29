"""Browser checks for the generated reading edition; no remote requests required."""
import argparse,json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--mobile-issues',nargs='+',type=int,default=[3,50,97,104,131,132,135,143,155,156])
parser.add_argument('--evidence',default='evidence/browser-design')
args=parser.parse_args()
out=(ROOT/args.evidence).resolve();out.mkdir(parents=True,exist_ok=True)
shots=out/'screenshots';shots.mkdir(exist_ok=True)
base=json.loads((ROOT/'evidence/preview-server.json').read_text())['url']
manifest=json.loads((ROOT/'preview/build-manifest.json').read_text())
articles=json.loads((ROOT/'preview/catalog.json').read_text(encoding='utf-8'))['articles']
routes=['' if path=='index.html' else path.removesuffix('index.html') for path in manifest['files'] if path.endswith('index.html')]
result={'pages':[],'errors':[],'checks':[],'screenshots':[]}
def check(name,passed,detail=None):
    result['checks'].append({'name':name,'passed':bool(passed),'detail':detail})
def screenshot(page,name,full=False):
    target=shots/(name+'.png')
    page.screenshot(path=str(target),full_page=full,animations='disabled')
    result['screenshots'].append(str(target.relative_to(out)))
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True,args=['--disable-gpu'])
    context=browser.new_context(viewport={'width':1440,'height':1000},device_scale_factor=1)
    # Reading pages should not need third-party requests for display or controls.
    context.route('**/*',lambda route: route.continue_() if route.request.url.startswith(base.split('/estrategia-english')[0]) else route.abort())
    page=context.new_page()
    page.on('pageerror',lambda error:result['errors'].append(str(error)))
    for width in [1440,768,320]:
        page.set_viewport_size({'width':width,'height':1000 if width==1440 else 900})
        for route in routes:
            response=page.goto(base+route,wait_until='domcontentloaded')
            page.evaluate('document.fonts.ready')
            layout=page.evaluate('''() => ({
                overflow:document.documentElement.scrollWidth>innerWidth+1,
                nestedInteractive:document.querySelectorAll('a button, button a').length,
                main:document.querySelectorAll('main').length,
                headings:document.querySelectorAll('h1').length,
                untitledControls:[...document.querySelectorAll('button,input,select')].filter(e=>!e.hidden && !e.innerText.trim() && !e.getAttribute('aria-label') && !(e.labels?.length)).length
            })''')
            result['pages'].append({'route':route,'width':width,'status':response.status,**layout})
            name=route.strip('/').replace('/','-') or 'home'
            if width==1440 and (route in ['', 'essays/','topics/','about/'] or route.startswith(('topics/','people/'))):
                screenshot(page,name+'-desktop',full=route in ['', 'topics/','about/'])
            if width==320 and route.startswith('essays/') and route!='essays/':
                screenshot(page,name+'-mobile-head')
        print(json.dumps({'checked_width':width,'pages':len(routes)}),flush=True)
    page.set_viewport_size({'width':390,'height':844})
    for route in ['', 'essays/','topics/','about/']+[r for r in routes if r.startswith('people/')]+[f'essays/{n:03d}/' for n in args.mobile_issues]:
        page.goto(base+route,wait_until='domcontentloaded')
        name=route.strip('/').replace('/','-') or 'home'
        screenshot(page,name+'-390')
        if route.startswith('essays/') and route!='essays/':
            body=page.locator('.article-body')
            body.scroll_into_view_if_needed()
            # Move to the beginning, not the centre, of the long article body.
            page.evaluate("document.querySelector('.article-body').scrollIntoView({block:'start',behavior:'instant'})")
            screenshot(page,name+'-390-reading')
            dimensions=page.locator('.article-body img').evaluate_all('(images)=>images.map(i=>({width:i.width,height:i.height,originalWidth:i.getAttribute("width"),originalHeight:i.getAttribute("height")}))')
            check(name+'-reserved-image-space',all(i['width']>0 and i['height']>0 for i in dimensions))
    for route in ['', 'essays/','topics/','about/','essays/003/','essays/104/','essays/132/','essays/155/']+[r for r in routes if r.startswith('people/')]:
        page.set_viewport_size({'width':1280,'height':900})
        page.goto(base+route,wait_until='domcontentloaded')
        page.add_style_tag(content='html{font-size:200%}')
        check('text-200-percent '+route,not page.evaluate('document.documentElement.scrollWidth>innerWidth+1'))
    # Keyboard entry into the main landmark and a real 404 response.
    page.goto(base,wait_until='domcontentloaded');page.keyboard.press('Tab')
    check('skip-link-first',page.locator('.skip').evaluate('(e)=>e===document.activeElement'))
    page.keyboard.press('Enter')
    check('skip-link-main-focus',page.evaluate('document.activeElement.id')=='main')
    response=page.goto(base+'does-not-exist/',wait_until='domcontentloaded')
    check('real-404',response.status==404)
    context.close()
    nojs=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
    page=nojs.new_page();page.goto(base+'essays/')
    check('all-153-visible-without-js',page.locator('[data-essay]:visible').count()==len(articles))
    check('inactive-search-hidden-without-js',not page.locator('#archive-filters').is_visible())
    page.goto(base+'essays/132/')
    check('reading-without-js',len(page.locator('.article-body').inner_text())>8000)
    check('native-toc-without-js',page.locator('details.reading-toc').get_attribute('open') is not None)
    check('no-inert-zoom-without-js',page.locator('.image-zoom:visible').count()==0)
    nojs.close();browser.close()
result['passed']=not result['errors'] and all(row['status']==200 and not row['overflow'] and not row['nestedInteractive'] and row['main']==row['headings']==1 and row['untitledControls']==0 for row in result['pages']) and all(row['passed'] for row in result['checks'])
for target in [ROOT/'evidence/QA_BROWSER.json',out/'BROWSER_QA.json']:
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':result['passed'],'pages':len(result['pages']),'checks':len(result['checks']),'screenshots':len(result['screenshots']),'failures':[r for r in result['pages'] if r['overflow'] or r['nestedInteractive'] or r['untitledControls']]+[r for r in result['checks'] if not r['passed']],'errors':result['errors']}))
raise SystemExit(0 if result['passed'] else 1)
