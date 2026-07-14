import os
import sys
import time
import uuid
import random
import signal
import logging
import asyncio
from typing import Optional, Tuple
from urllib.parse import urlsplit
import argparse
from quart import Quart, request, jsonify
from patchright.async_api import async_playwright
from db_results import init_db, save_result, load_result, cleanup_old_results
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich import box


COLORS = {
    'MAGENTA': '\033[35m',
    'BLUE': '\033[34m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'RED': '\033[31m',
    'RESET': '\033[0m',
}

CHROMIUM_LIKE = ('chromium', 'chrome', 'msedge')

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
CHROME_SEC_CH_UA = (
    '"Chromium";v="150", "Not=A?Brand";v="24", "Google Chrome";v="150"'
)

# waguri turnstile/template.html
HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Turnstile</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #1a1a1a; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
</style>
</head>
<body>
<!--WIDGET-->
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
</body></html>"""

WIDGET_INJECT_JS = (
    "(k) => {"
    " const d = document.createElement('div');"
    " d.className = 'cf-turnstile';"
    " d.setAttribute('data-sitekey', k);"
    " document.body.prepend(d);"
    "}"
)


def route_glob(url: str) -> str:
    parts = urlsplit(url)
    if parts.path in ('', '/'):
        return f'{parts.scheme}://{parts.netloc}/**'
    return url


def build_route_html(sitekey: str) -> str:
    div = f'<div class="cf-turnstile" data-sitekey="{sitekey}"></div>'
    return HTML_TEMPLATE.replace('<!--WIDGET-->', div)


class CustomLogger(logging.Logger):
    @staticmethod
    def format_message(level, color, message):
        timestamp = time.strftime('%H:%M:%S')
        return f"[{timestamp}] [{COLORS.get(color)}{level}{COLORS.get('RESET')}] -> {message}"

    def debug(self, message, *args, **kwargs):
        super().debug(self.format_message('DEBUG', 'MAGENTA', message), *args, **kwargs)

    def info(self, message, *args, **kwargs):
        super().info(self.format_message('INFO', 'BLUE', message), *args, **kwargs)

    def success(self, message, *args, **kwargs):
        super().info(self.format_message('SUCCESS', 'GREEN', message), *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        super().warning(self.format_message('WARNING', 'YELLOW', message), *args, **kwargs)

    def error(self, message, *args, **kwargs):
        super().error(self.format_message('ERROR', 'RED', message), *args, **kwargs)


logging.setLoggerClass(CustomLogger)
logger = logging.getLogger("TurnstileAPIServer")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)


class TurnstileAPIServer:

    def __init__(self, headless: bool, useragent: Optional[str], debug: bool,
                 browser_type: str, thread: int, proxy_support: bool):
        self.app = Quart(__name__)
        self.debug = debug
        self.browser_type = browser_type
        self.headless = headless
        self.thread_count = thread
        self.proxy_support = proxy_support
        self.useragent = useragent
        self.sec_ch_ua = None
        if self.browser_type in CHROMIUM_LIKE and self.headless:
            if not self.useragent:
                self.useragent = CHROME_USER_AGENT
            self.sec_ch_ua = CHROME_SEC_CH_UA
        self._semaphore = asyncio.Semaphore(thread)
        self.console = Console()
        self._setup_routes()

    def display_welcome(self):
        self.console.clear()
        combined_text = Text()
        combined_text.append("\n📢 Channel: ", style="bold white")
        combined_text.append("https://t.me/D3_vin", style="cyan")
        combined_text.append("\n💬 Chat: ", style="bold white")
        combined_text.append("https://t.me/D3vin_chat", style="cyan")
        combined_text.append("\n📁 GitHub: ", style="bold white")
        combined_text.append("https://github.com/D3-vin", style="cyan")
        combined_text.append("\n📁 Version: ", style="bold white")
        combined_text.append("1.3", style="green")
        combined_text.append("\n")

        info_panel = Panel(
            Align.left(combined_text),
            title="[bold blue]Turnstile Solver[/bold blue]",
            subtitle="[bold magenta]Dev by D3vin[/bold magenta]",
            box=box.ROUNDED,
            border_style="bright_blue",
            padding=(0, 1),
            width=50,
        )
        self.console.print(info_panel)
        self.console.print()

    def _setup_routes(self) -> None:
        self.app.before_serving(self._startup)
        self.app.route('/turnstile', methods=['GET'])(self.process_turnstile)
        self.app.route('/result', methods=['GET'])(self.get_result)
        self.app.route('/')(self.index)

    async def _startup(self) -> None:
        self.display_welcome()
        await init_db()
        asyncio.create_task(self._periodic_cleanup())
        logger.info(
            f"Ready: {self.browser_type}, "
            f"headless={'new' if self.headless else 'off (--no-headless)'}, "
            f"max concurrent={self.thread_count}"
        )

    async def _periodic_cleanup(self):
        while True:
            try:
                await asyncio.sleep(3600)
                deleted_count = await cleanup_old_results(days_old=7)
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old results")
            except Exception as e:
                logger.error(f"Error during periodic cleanup: {e}")

    def _chromium_launch_kwargs(self) -> dict:
        args = ['--headless=new'] if self.headless else []
        return {'headless': False, 'args': args}

    def _context_options(self, proxy: Optional[str]) -> dict:
        opts = {'viewport': {'width': 600, 'height': 250}}
        if self.browser_type in CHROMIUM_LIKE and self.headless:
            if self.useragent:
                opts['user_agent'] = self.useragent
            if self.sec_ch_ua:
                opts['extra_http_headers'] = {
                    'sec-ch-ua': self.sec_ch_ua,
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                }
        elif self.useragent:
            opts['user_agent'] = self.useragent
        if proxy:
            opts['proxy'] = self._parse_proxy(proxy)
        return opts

    async def _launch_browser(self) -> Tuple[object, object]:
        if self.browser_type == 'camoufox':
            from camoufox.async_api import AsyncCamoufox
            driver = AsyncCamoufox(headless=self.headless)
            browser = await driver.start()
            return driver, browser

        driver = await async_playwright().start()
        browser = await driver.chromium.launch(
            channel=self.browser_type,
            **self._chromium_launch_kwargs(),
        )
        return driver, browser

    async def _close_browser(self, driver, browser) -> None:
        try:
            if browser:
                await browser.close()
        except Exception as e:
            if self.debug:
                logger.debug(f"Browser close error: {e}")
        try:
            if driver and hasattr(driver, 'stop'):
                await driver.stop()
        except Exception as e:
            if self.debug:
                logger.debug(f"Driver stop error: {e}")

    def _parse_proxy(self, proxy: str) -> dict:
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

    async def _pick_proxy(self) -> Optional[str]:
        if not self.proxy_support:
            return None
        path = os.path.join(os.getcwd(), 'proxies.txt')
        try:
            with open(path) as f:
                proxies = [line.strip() for line in f if line.strip()]
            return random.choice(proxies) if proxies else None
        except FileNotFoundError:
            logger.warning(f"Proxy file not found: {path}")
            return None

    async def _human_click_iframe(self, page, frame) -> bool:
        try:
            el = await frame.frame_element()
            box = await el.bounding_box()
        except Exception:
            return False
        if not box or box['width'] < 20:
            return False
        x = box['x'] + 30
        y = box['y'] + box['height'] / 2
        await page.mouse.click(x, y)
        return True

    async def _click_turnstile_checkbox(self, page, attempts: int = 25) -> bool:
        for _ in range(attempts):
            for fr in page.frames:
                if 'challenges.cloudflare.com' in (fr.url or ''):
                    if await self._human_click_iframe(page, fr):
                        return True
                    for sel in ('input[type=checkbox]', 'label', 'body'):
                        try:
                            await fr.click(sel, timeout=2000)
                            return True
                        except Exception:
                            continue
            await asyncio.sleep(1)
        return False

    async def _get_turnstile_response_route(self, page, max_attempts: int = 20) -> Optional[str]:
        """waguri _get_turnstile_response_route"""
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
                    if el:
                        return await el.get_attribute('value')
                    break
            except Exception:
                await asyncio.sleep(1)
        return None

    async def solve_turnstile_route(self, page, url: str, sitekey: str) -> Optional[str]:
        """waguri solve_turnstile"""
        page_data = build_route_html(sitekey)
        pattern = route_glob(url)
        await page.route(pattern, lambda r: r.fulfill(body=page_data, status=200))
        logger.info(f"Route-intercept {pattern}")
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        return await self._get_turnstile_response_route(page), pattern

    async def solve_turnstile_realpage(self, page, url: str, sitekey: str,
                                       timeout_s: int = 60) -> Optional[str]:
        """waguri solve_turnstile_realpage (without pre_actions/post_fetch)"""
        logger.info(f"Real-page {url}")
        await page.goto(url, wait_until='domcontentloaded', timeout=45000)
        await asyncio.sleep(2)

        if sitekey:
            await page.evaluate(WIDGET_INJECT_JS, sitekey)
            await asyncio.sleep(3)

        clicked = await self._click_turnstile_checkbox(page)
        if self.debug:
            logger.debug(f"Checkbox clicked={clicked}")

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                token = await page.evaluate(
                    "() => { const e=document.querySelector('[name=cf-turnstile-response]');"
                    " return e ? e.value : '' }"
                )
            except Exception:
                token = ''
            if token:
                return token
            await asyncio.sleep(1)
        return None

    async def _solve_turnstile(self, task_id: str, url: str, sitekey: str,
                               action: Optional[str] = None, cdata: Optional[str] = None):
        async with self._semaphore:
            driver = None
            browser = None
            context = None
            start_time = time.time()
            proxy = await self._pick_proxy()

            try:
                driver, browser = await self._launch_browser()
                context = await browser.new_context(**self._context_options(proxy))
                page = await context.new_page()

                if self.debug:
                    logger.debug(f"Solve url={url} sitekey={sitekey} proxy={proxy}")

                token, route_pattern = await self.solve_turnstile_route(page, url, sitekey)
                method = 'route'

                if not token:
                    logger.info("Route failed, trying real-page")
                    await page.unroute(route_pattern)
                    token = await self.solve_turnstile_realpage(page, url, sitekey)
                    method = 'real-page'

                if token:
                    elapsed = round(time.time() - start_time, 3)
                    logger.success(
                        f"Solved via {method} - {COLORS.get('MAGENTA')}{token[:10]}"
                        f"{COLORS.get('RESET')} in {COLORS.get('GREEN')}{elapsed}{COLORS.get('RESET')}s"
                    )
                    await save_result(task_id, "turnstile", {"value": token, "elapsed_time": elapsed})
                    return

                elapsed = round(time.time() - start_time, 3)
                await save_result(task_id, "turnstile", {"value": "CAPTCHA_FAIL", "elapsed_time": elapsed})
                logger.error(f"CAPTCHA_FAIL in {elapsed}s")
            except Exception as e:
                elapsed = round(time.time() - start_time, 3)
                await save_result(task_id, "turnstile", {"value": "CAPTCHA_FAIL", "elapsed_time": elapsed})
                logger.error(f"Solve error: {e}")
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
                await self._close_browser(driver, browser)

    async def process_turnstile(self):
        url = request.args.get('url')
        sitekey = request.args.get('sitekey')
        action = request.args.get('action')
        cdata = request.args.get('cdata')

        if not url or not sitekey:
            return jsonify({
                "errorId": 1,
                "errorCode": "ERROR_WRONG_PAGEURL",
                "errorDescription": "Both 'url' and 'sitekey' are required",
            }), 200

        task_id = str(uuid.uuid4())
        await save_result(task_id, "turnstile", {
            "status": "CAPTCHA_NOT_READY",
            "createTime": int(time.time()),
            "url": url,
            "sitekey": sitekey,
            "action": action,
            "cdata": cdata,
        })

        asyncio.create_task(self._solve_turnstile(
            task_id=task_id, url=url, sitekey=sitekey, action=action, cdata=cdata,
        ))
        return jsonify({"errorId": 0, "taskId": task_id}), 200

    async def get_result(self):
        task_id = request.args.get('id')
        if not task_id:
            return jsonify({
                "errorId": 1,
                "errorCode": "ERROR_WRONG_CAPTCHA_ID",
                "errorDescription": "Invalid task ID/Request parameter",
            }), 200

        result = await load_result(task_id)
        if not result:
            return jsonify({
                "errorId": 1,
                "errorCode": "ERROR_CAPTCHA_UNSOLVABLE",
                "errorDescription": "Task not found",
            }), 200

        if result == "CAPTCHA_NOT_READY" or (
            isinstance(result, dict) and result.get("status") == "CAPTCHA_NOT_READY"
        ):
            return jsonify({"status": "processing"}), 200

        if isinstance(result, dict) and result.get("value") == "CAPTCHA_FAIL":
            return jsonify({
                "errorId": 1,
                "errorCode": "ERROR_CAPTCHA_UNSOLVABLE",
                "errorDescription": "Workers could not solve the Captcha",
            }), 200

        if isinstance(result, dict) and result.get("value") and result.get("value") != "CAPTCHA_FAIL":
            return jsonify({
                "errorId": 0,
                "status": "ready",
                "solution": {"token": result["value"]},
            }), 200

        return jsonify({
            "errorId": 1,
            "errorCode": "ERROR_CAPTCHA_UNSOLVABLE",
            "errorDescription": "Workers could not solve the Captcha",
        }), 200

    @staticmethod
    async def index():
        """Serve the API documentation page."""
        return """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Turnstile Solver API</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="bg-gray-900 text-gray-200 min-h-screen flex items-center justify-center">
                <div class="bg-gray-800 p-8 rounded-lg shadow-md max-w-2xl w-full border border-red-500">
                    <h1 class="text-3xl font-bold mb-6 text-center text-red-500">Welcome to Turnstile Solver API</h1>

                    <p class="mb-4 text-gray-300">To use the turnstile service, send a GET request to 
                       <code class="bg-red-700 text-white px-2 py-1 rounded">/turnstile</code> with the following query parameters:</p>

                    <ul class="list-disc pl-6 mb-6 text-gray-300">
                        <li><strong>url</strong>: The URL where Turnstile is to be validated</li>
                        <li><strong>sitekey</strong>: The site key for Turnstile</li>
                    </ul>

                    <div class="bg-gray-700 p-4 rounded-lg mb-6 border border-red-500">
                        <p class="font-semibold mb-2 text-red-400">Example usage:</p>
                        <code class="text-sm break-all text-red-300">/turnstile?url=https://example.com&sitekey=sitekey</code>
                    </div>


                    <div class="bg-gray-700 p-4 rounded-lg mb-6">
                        <p class="text-gray-200 font-semibold mb-3">📢 Connect with Us</p>
                        <div class="space-y-2 text-sm">
                            <p class="text-gray-300">
                                📢 <strong>Channel:</strong> 
                                <a href="https://t.me/D3_vin" class="text-red-300 hover:underline">https://t.me/D3_vin</a> 
                                - Latest updates and releases
                            </p>
                            <p class="text-gray-300">
                                💬 <strong>Chat:</strong> 
                                <a href="https://t.me/D3vin_chat" class="text-red-300 hover:underline">https://t.me/D3vin_chat</a> 
                                - Community support and discussions
                            </p>
                            <p class="text-gray-300">
                                📁 <strong>GitHub:</strong> 
                                <a href="https://github.com/D3-vin" class="text-red-300 hover:underline">https://github.com/D3-vin</a> 
                                - Source code and development
                            </p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
        """


def parse_args():
    parser = argparse.ArgumentParser(description="Turnstile API Server")
    parser.add_argument('--no-headless', action='store_true',
                        help='Показать браузер (по умолчанию headless)')
    parser.add_argument('--useragent', type=str,
                        help='Свой User-Agent (headless: по умолчанию Chrome 150 + sec-ch-ua)')
    parser.add_argument('--debug', action='store_true', help='Debug logging')
    parser.add_argument('--browser_type', type=str, default='chrome',
                        help='chromium, chrome, msedge, camoufox')
    parser.add_argument('--thread', type=int, default=4, help='Max concurrent solves')
    parser.add_argument('--proxy', action='store_true', help='Use proxies.txt')
    parser.add_argument('--host', type=str, default='0.0.0.0')
    parser.add_argument('--port', type=str, default='5072')
    return parser.parse_args()


def create_app(headless, useragent, debug, browser_type, thread, proxy_support):
    return TurnstileAPIServer(
        headless=headless, useragent=useragent, debug=debug,
        browser_type=browser_type, thread=thread, proxy_support=proxy_support,
    ).app


def _kill_child_processes() -> None:
    try:
        import psutil
        for child in psutil.Process(os.getpid()).children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
    except Exception:
        pass


if __name__ == '__main__':
    args = parse_args()
    if args.browser_type not in ('chromium', 'chrome', 'msedge', 'camoufox'):
        logger.error(f"Unknown browser type: {args.browser_type}")
    else:
        server = TurnstileAPIServer(
            headless=not args.no_headless,
            debug=args.debug,
            useragent=args.useragent,
            browser_type=args.browser_type,
            thread=args.thread,
            proxy_support=args.proxy,
        )

        def emergency_shutdown(sig, frame):
            logger.warning("Ctrl+C — завершение, закрываю браузеры...")
            _kill_child_processes()
            os._exit(0)

        signal.signal(signal.SIGINT, emergency_shutdown)
        signal.signal(signal.SIGTERM, emergency_shutdown)

        try:
            server.app.run(host=args.host, port=int(args.port))
        except KeyboardInterrupt:
            emergency_shutdown(None, None)
