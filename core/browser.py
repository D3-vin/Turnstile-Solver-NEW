import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from patchright.async_api import async_playwright

from .logger import get_logger

logger = get_logger()

CHROMIUM_LIKE = ('chromium', 'chrome', 'msedge')

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
CHROME_SEC_CH_UA = (
    '"Chromium";v="150", "Not=A?Brand";v="24", "Google Chrome";v="150"'
)

PROXIES_PATH = Path(__file__).resolve().parent.parent / 'proxies.txt'


@dataclass
class BrowserConfig:
    browser_type: str = 'chrome'
    headless: bool = True
    useragent: Optional[str] = None
    sec_ch_ua: Optional[str] = None
    proxy_support: bool = False
    debug: bool = False

    def __post_init__(self) -> None:
        if self.browser_type in CHROMIUM_LIKE and self.headless:
            if not self.useragent:
                self.useragent = CHROME_USER_AGENT
            self.sec_ch_ua = CHROME_SEC_CH_UA


def parse_proxy(proxy: str) -> dict:
    if '://' not in proxy:
        proxy = f'http://{proxy}'
    scheme, rest = proxy.split('://', 1)
    if '@' in rest:
        auth, addr = rest.split('@', 1)
        user, pwd = auth.split(':', 1)
        return {'server': f'{scheme}://{addr}', 'username': user, 'password': pwd}
    parts = rest.split(':')
    if len(parts) == 5:
        return {
            'server': f'{parts[0]}://{parts[1]}:{parts[2]}',
            'username': parts[3],
            'password': parts[4],
        }
    return {'server': proxy}


def pick_proxy(proxy_support: bool) -> Optional[str]:
    if not proxy_support:
        return None
    try:
        proxies = [line.strip() for line in PROXIES_PATH.read_text().splitlines() if line.strip()]
        return random.choice(proxies) if proxies else None
    except FileNotFoundError:
        logger.warning(f"Proxy file not found: {PROXIES_PATH}")
        return None


async def launch_browser(config: BrowserConfig) -> Tuple[object, object]:
    if config.browser_type == 'camoufox':
        from camoufox.async_api import AsyncCamoufox
        driver = AsyncCamoufox(headless=config.headless)
        browser = await driver.start()
        return driver, browser

    driver = await async_playwright().start()
    args = ['--headless=new'] if config.headless else []
    browser = await driver.chromium.launch(channel=config.browser_type, headless=False, args=args)
    return driver, browser


def context_options(config: BrowserConfig, proxy: Optional[str]) -> dict:
    opts = {'viewport': {'width': 600, 'height': 250}}
    if config.browser_type in CHROMIUM_LIKE and config.headless:
        if config.useragent:
            opts['user_agent'] = config.useragent
        if config.sec_ch_ua:
            opts['extra_http_headers'] = {
                'sec-ch-ua': config.sec_ch_ua,
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
            }
    elif config.useragent:
        opts['user_agent'] = config.useragent
    if proxy:
        opts['proxy'] = parse_proxy(proxy)
    return opts


async def close_browser(driver, browser, debug: bool = False) -> None:
    try:
        if browser:
            await browser.close()
    except Exception as e:
        if debug:
            logger.debug(f"Browser close error: {e}")
    try:
        if driver and hasattr(driver, 'stop'):
            await driver.stop()
    except Exception as e:
        if debug:
            logger.debug(f"Driver stop error: {e}")
