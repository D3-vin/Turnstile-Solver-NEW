import asyncio
import time
from typing import Optional, Tuple

from core.logger import get_logger
from core.templates import TOKEN_VALUE_JS, WIDGET_INJECT_JS, build_route_html, route_glob

logger = get_logger()


async def _human_click_iframe(page, frame) -> bool:
    try:
        el = await frame.frame_element()
        box = await el.bounding_box()
    except Exception:
        return False
    if not box or box['width'] < 20:
        return False
    await page.mouse.click(box['x'] + 30, box['y'] + box['height'] / 2)
    return True


async def click_turnstile_checkbox(page, attempts: int = 25) -> bool:
    for _ in range(attempts):
        for fr in page.frames:
            if 'challenges.cloudflare.com' not in (fr.url or ''):
                continue
            if await _human_click_iframe(page, fr):
                return True
            for sel in ('input[type=checkbox]', 'label', 'body'):
                try:
                    await fr.click(sel, timeout=2000)
                    return True
                except Exception:
                    continue
        await asyncio.sleep(1)
    return False


async def _get_token_route(page, max_attempts: int = 20) -> Optional[str]:
    for _ in range(max_attempts):
        try:
            val = await page.input_value('[name=cf-turnstile-response]')
            if val == '':
                try:
                    await page.click('//div[@class="cf-turnstile"]', timeout=3000)
                except Exception:
                    pass
                await asyncio.sleep(1)
            else:
                el = await page.query_selector('[name=cf-turnstile-response]')
                return await el.get_attribute('value') if el else None
        except Exception:
            await asyncio.sleep(1)
    return None


async def solve_route(page, url: str, sitekey: str, action: Optional[str] = None,
                      cdata: Optional[str] = None) -> Tuple[Optional[str], str]:
    page_data = build_route_html(sitekey, action, cdata)
    pattern = route_glob(url)
    await page.route(pattern, lambda r: r.fulfill(body=page_data, status=200))
    logger.info(f"Route-intercept {pattern}")
    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    return await _get_token_route(page), pattern


async def solve_realpage(page, url: str, sitekey: str, timeout_s: int = 60) -> Optional[str]:
    logger.info(f"Real-page {url}")
    await page.goto(url, wait_until='domcontentloaded', timeout=45000)
    await asyncio.sleep(2)

    if sitekey:
        await page.evaluate(WIDGET_INJECT_JS, sitekey)
        await asyncio.sleep(3)

    await click_turnstile_checkbox(page)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            token = await page.evaluate(TOKEN_VALUE_JS)
        except Exception:
            token = ''
        if token:
            return token
        await asyncio.sleep(1)
    return None


async def solve(page, url: str, sitekey: str, action: Optional[str] = None,
                cdata: Optional[str] = None) -> Tuple[Optional[str], str]:
    """Route-intercept first, real page as fallback. Returns (token, method)."""
    token, pattern = await solve_route(page, url, sitekey, action, cdata)
    if token:
        return token, 'route'
    logger.info("Route failed, trying real-page")
    await page.unroute(pattern)
    token = await solve_realpage(page, url, sitekey)
    return token, 'real-page'
