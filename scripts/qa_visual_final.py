import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / 'evidence' / 'preview-server.json').read_text(encoding='utf-8'))['url']
OUT = ROOT / 'evidence' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
result = {'base': BASE, 'screenshots': [], 'checks': {}, 'console_errors': []}

def capture(page, name):
    path = OUT / name
    page.screenshot(path=str(path), full_page=False)
    result['screenshots'].append({'file': str(path.relative_to(ROOT)), 'url': page.url, 'viewport': page.viewport_size, 'scroll_y': page.evaluate('scrollY'), 'horizontal_overflow': page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')})

def navigate(page, route):
    response = page.goto(BASE + route, wait_until='networkidle')
    assert response.status == 200, (route, response.status)

def position(page, selector, offset=24):
    page.locator(selector).first.evaluate('(el, offset) => window.scrollTo({top: el.getBoundingClientRect().top + scrollY - offset, behavior: "instant"})', offset)

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context(viewport={'width': 320, 'height': 844}, device_scale_factor=1, permissions=['clipboard-read', 'clipboard-write'])
    page = context.new_page()
    page.on('pageerror', lambda error: result['console_errors'].append(str(error)))

    navigate(page, 'essays/155/')
    capture(page, 'visual-155-mobile320-top.png')

    page.set_viewport_size({'width': 390, 'height': 844})
    position(page, '.article-body h2')
    capture(page, 'visual-155-mobile390-body.png')

    navigate(page, 'essays/104/')
    imgs = page.locator('.article-body img')
    assert imgs.count() == 2, imgs.count()
    for i in range(2):
        img = imgs.nth(i)
        img.evaluate('(el) => window.scrollTo({top: el.getBoundingClientRect().top + scrollY - 20, behavior: "instant"})')
        capture(page, f'visual-104-mobile390-image{i+1}.png')
    result['checks']['104_images'] = imgs.evaluate_all('(imgs) => imgs.map(i => ({loaded: i.complete && i.naturalWidth > 0, alt: i.alt, width: i.getBoundingClientRect().width, naturalWidth: i.naturalWidth}))')

    page.set_viewport_size({'width': 1440, 'height': 1000})
    navigate(page, 'about/')
    capture(page, 'visual-about-desktop-top.png')

    navigate(page, 'essays/155/')
    page.keyboard.press('Tab')
    result['checks']['skip_first_tab'] = page.evaluate('''() => {const a=document.activeElement,s=getComputedStyle(a),r=a.getBoundingClientRect();return {text:a.textContent.trim(),href:a.getAttribute('href'),visible:r.top>=0&&r.bottom<=innerHeight,outlineStyle:s.outlineStyle,outlineWidth:s.outlineWidth,outlineColor:s.outlineColor};}''')
    capture(page, 'visual-keyboard-skip-focus.png')
    page.keyboard.press('Enter')
    page.wait_for_timeout(300)
    result['checks']['skip_target'] = {'hash': page.evaluate('location.hash'), 'main_top': page.locator('#main').evaluate('(el)=>el.getBoundingClientRect().top')}
    page.keyboard.press('Tab')
    result['checks']['skip_next_focus'] = page.evaluate('''() => {const a=document.activeElement,s=getComputedStyle(a);return {text:a.textContent.trim(),withinMain:!!a.closest('main'),outlineStyle:s.outlineStyle,outlineWidth:s.outlineWidth};}''')
    capture(page, 'visual-keyboard-after-skip.png')

    # Reach the citation control by keyboard only, keeping the skip target as the start.
    count = 0
    while count < 150 and not page.evaluate('document.activeElement.matches("button[data-copy]")'):
        page.keyboard.press('Tab')
        count += 1
    assert count < 150, 'Citation control not reached by keyboard'
    page.wait_for_function("() => {const r=document.activeElement.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight;}", timeout=5000)
    page.wait_for_timeout(600)  # Allow the page's smooth scroll to settle before capturing focus.
    result['checks']['copy_keyboard_focus'] = page.evaluate('''() => {const a=document.activeElement,s=getComputedStyle(a);return {text:a.textContent.trim(),outlineStyle:s.outlineStyle,outlineWidth:s.outlineWidth,outlineColor:s.outlineColor};}''')
    capture(page, 'visual-keyboard-copy-focus.png')
    expected = page.locator('#citation-text').inner_text().strip()
    page.keyboard.press('Enter')
    page.wait_for_function('document.querySelector(".citation [role=status]").textContent.length > 0')
    copied = page.evaluate('navigator.clipboard.readText()')
    result['checks']['copy_citation'] = {'keyboard_tabs_from_skip': count, 'matches_expected': copied == expected, 'status': page.locator('.citation [role=status]').inner_text(), 'copied_text': copied, 'aria_live': page.locator('.citation [role=status]').get_attribute('aria-live'), 'permissions': 'clipboard-read and clipboard-write granted in test browser; no clipboard mocks'}
    capture(page, 'visual-citation-copied.png')
    browser.close()

(ROOT / 'evidence' / 'QA_VISUAL_RUNTIME.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'screenshots': len(result['screenshots']), 'checks': result['checks'], 'console_errors': result['console_errors']}, ensure_ascii=True))
