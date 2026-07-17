import asyncio
import time
from typing import Optional, Tuple

from core.logger import get_logger
from turnstile.solve import click_turnstile_checkbox

logger = get_logger()

CF_MARKERS_JS = r"""() => {
  const html = document.documentElement.outerHTML;
  const t = (document.title || '').toLowerCase();
  return (
    !!document.querySelector('#challenge-form, form#challenge-form') ||
    !!document.querySelector('#cf-wrapper, .cf-browser-verification, #challenge-running, #trk_jschal_js') ||
    !!document.querySelector('iframe[src*="challenges.cloudflare.com"]') ||
    /window\._cf_chl_opt|__cf_chl_/.test(html) ||
    /just a moment|attention required|checking your browser|verifying you are human/.test(t)
  );
}"""

REPLAY_WARNING = (
    "cf_clearance is bound to IP + JA3/TLS + User-Agent. Replay only from the "
    "same IP, with this exact User-Agent, over a TLS stack producing the same JA3."
)


def find_clearance(cookies: list) -> Optional[dict]:
    return next((c for c in cookies if c.get('name') == 'cf_clearance'), None)


async def is_interstitial(page) -> bool:
    try:
        return bool(await page.evaluate(CF_MARKERS_JS))
    except Exception:
        return False


async def _wait_clearance(page, timeout_s: int) -> Tuple[Optional[dict], list]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        cookies = await page.context.cookies()
        clearance = find_clearance(cookies)
        if clearance and not await is_interstitial(page):
            return clearance, cookies
        if clearance:
            await asyncio.sleep(1)
            cookies = await page.context.cookies()
            return find_clearance(cookies), cookies
        await asyncio.sleep(1)
    return None, await page.context.cookies()


async def solve(page, url: str, timeout_s: int = 60) -> dict:
    """Pass the Cloudflare interstitial on a real page and harvest cf_clearance."""
    start = time.monotonic()
    await page.goto(url, wait_until='domcontentloaded', timeout=45000)

    try:
        await click_turnstile_checkbox(page, attempts=8)
    except Exception:
        pass

    clearance, cookies = await _wait_clearance(page, timeout_s)
    ua = await page.evaluate('() => navigator.userAgent')
    lang = await page.evaluate('() => navigator.language')

    result = {
        'cf_clearance': clearance,
        'cookies': cookies,
        'user_agent': ua,
        'headers': {'User-Agent': ua, 'Accept-Language': lang},
        'elapsed': round(time.monotonic() - start, 1),
        'warning': REPLAY_WARNING,
    }
    if not clearance:
        result['error'] = 'cf_clearance not set (challenge unsolved)'
    return result
