import argparse
import asyncio
import logging
import os
import signal
import time
import uuid
from typing import Awaitable, Callable, Optional

from quart import Quart, jsonify, request
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

import cf_clearance.solve as cf_clearance_solver
import turnstile.solve as turnstile_solver
from core.browser import (
    BrowserConfig,
    close_browser,
    context_options,
    launch_browser,
    pick_proxy,
)
from core.logger import COLORS, get_logger

logger = get_logger("SolverAPI")

TASKS: dict = {}
TASK_TTL_S = 3600
CLEANUP_INTERVAL_S = 600

INDEX_HTML = """
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

        <p class="mb-4 text-gray-300">Send a GET request to
           <code class="bg-red-700 text-white px-2 py-1 rounded">/turnstile</code> with query parameters:</p>
        <ul class="list-disc pl-6 mb-6 text-gray-300">
            <li><strong>url</strong>: The URL where Turnstile is to be validated</li>
            <li><strong>sitekey</strong>: The site key for Turnstile</li>
            <li><strong>action</strong> / <strong>cdata</strong>: optional widget bindings</li>
        </ul>
        <div class="bg-gray-700 p-4 rounded-lg mb-6 border border-red-500">
            <p class="font-semibold mb-2 text-red-400">Example usage:</p>
            <code class="text-sm break-all text-red-300">/turnstile?url=https://example.com&sitekey=sitekey</code>
        </div>

        <p class="mb-4 text-gray-300">To pass a Cloudflare interstitial (IUAM) and harvest
           <strong>cf_clearance</strong>, use
           <code class="bg-red-700 text-white px-2 py-1 rounded">/cf_clearance</code>:</p>
        <ul class="list-disc pl-6 mb-6 text-gray-300">
            <li><strong>url</strong>: The protected page URL</li>
            <li><strong>proxy</strong>: optional per-request proxy (cf_clearance is bound to the exit IP)</li>
            <li><strong>timeout</strong>: optional, seconds (default 60)</li>
        </ul>
        <div class="bg-gray-700 p-4 rounded-lg mb-6 border border-red-500">
            <p class="font-semibold mb-2 text-red-400">Example usage:</p>
            <code class="text-sm break-all text-red-300">/cf_clearance?url=https://example.com&proxy=http://user:pass@ip:port</code>
        </div>

        <p class="mb-6 text-gray-300">Poll <code class="bg-red-700 text-white px-2 py-1 rounded">/result?id=taskId</code>
           until <strong>status</strong> is <strong>ready</strong>.</p>

        <div class="bg-gray-700 p-4 rounded-lg mb-6">
            <p class="text-gray-200 font-semibold mb-3">Connect with Us</p>
            <div class="space-y-2 text-sm">
                <p class="text-gray-300">
                    Channel:
                    <a href="https://t.me/D3_vin" class="text-red-300 hover:underline">https://t.me/D3_vin</a>
                </p>
                <p class="text-gray-300">
                    Chat:
                    <a href="https://t.me/D3vin_chat" class="text-red-300 hover:underline">https://t.me/D3vin_chat</a>
                </p>
                <p class="text-gray-300">
                    GitHub:
                    <a href="https://github.com/D3-vin" class="text-red-300 hover:underline">https://github.com/D3-vin</a>
                </p>
            </div>
        </div>
    </div>
</body>
</html>
"""


def display_welcome() -> None:
    console = Console()
    console.clear()
    combined_text = Text()
    combined_text.append("\n📢 Channel: ", style="bold white")
    combined_text.append("https://t.me/D3_vin", style="cyan")
    combined_text.append("\n💬 Chat: ", style="bold white")
    combined_text.append("https://t.me/D3vin_chat", style="cyan")
    combined_text.append("\n📁 GitHub: ", style="bold white")
    combined_text.append("https://github.com/D3-vin", style="cyan")
    combined_text.append("\n📁 Version: ", style="bold white")
    combined_text.append("2.0", style="green")
    combined_text.append("\n")

    info_panel = Panel(
        Align.left(combined_text),
        title="[bold blue]Turnstile + Challenge[/bold blue]",
        subtitle="[bold magenta]Dev by D3vin[/bold magenta]",
        box=box.ROUNDED,
        border_style="bright_blue",
        padding=(0, 1),
        width=50,
    )
    console.print(info_panel)
    console.print()


def _new_task(task_type: str, **meta) -> str:
    task_id = str(uuid.uuid4())
    TASKS[task_id] = {
        'status': 'processing',
        'type': task_type,
        'created': time.time(),
        **meta,
    }
    return task_id


async def _periodic_cleanup() -> None:
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_S)
            cutoff = time.time() - TASK_TTL_S
            stale = [tid for tid, t in TASKS.items() if t['created'] < cutoff]
            for tid in stale:
                TASKS.pop(tid, None)
            if stale:
                logger.info(f"Cleaned up {len(stale)} old tasks")
        except Exception as e:
            logger.error(f"Error during periodic cleanup: {e}")


async def _turnstile_job(page, url: str, sitekey: str,
                         action: Optional[str], cdata: Optional[str]) -> Optional[dict]:
    token, method = await turnstile_solver.solve(page, url, sitekey, action, cdata)
    if not token:
        return None
    return {'token': token, 'method': method}


async def _cf_clearance_job(page, url: str, proxy: Optional[str], timeout_s: int) -> Optional[dict]:
    bundle = await cf_clearance_solver.solve(page, url, timeout_s)
    if not bundle.get('cf_clearance'):
        return None
    bundle['proxy'] = proxy
    return bundle


async def _run_solve(task_id: str, job: Callable[..., Awaitable[Optional[dict]]],
                     config: BrowserConfig, semaphore: asyncio.Semaphore,
                     proxy: Optional[str]) -> None:
    async with semaphore:
        driver = browser = context = None
        start = time.time()
        try:
            driver, browser = await launch_browser(config)
            context = await browser.new_context(**context_options(config, proxy))
            page = await context.new_page()
            if config.debug:
                logger.debug(f"Solve task={task_id} proxy={proxy}")

            result = await job(page)
            elapsed = round(time.time() - start, 3)

            if result is None:
                TASKS[task_id].update(status='fail', elapsed=elapsed)
                logger.error(f"CAPTCHA_FAIL in {elapsed}s")
            else:
                result['elapsed_time'] = elapsed
                TASKS[task_id].update(status='ready', result=result)
                logger.success(
                    f"Solved - {COLORS['MAGENTA']}{task_id[:8]}"
                    f"{COLORS['RESET']} in {COLORS['GREEN']}{elapsed}{COLORS['RESET']}s"
                )
        except Exception as e:
            TASKS[task_id].update(status='fail', elapsed=round(time.time() - start, 3))
            logger.error(f"Solve error: {e}")
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            await close_browser(driver, browser, config.debug)


def create_app(config: BrowserConfig, threads: int = 4) -> Quart:
    app = Quart(__name__)
    semaphore = asyncio.Semaphore(threads)

    @app.before_serving
    async def startup() -> None:
        display_welcome()
        if not config.debug:
            logging.getLogger('hypercorn.access').disabled = True
        asyncio.create_task(_periodic_cleanup())
        logger.info(
            f"Ready: {config.browser_type}, "
            f"headless={'new' if config.headless else 'off (--no-headless)'}, "
            f"max concurrent={threads}"
        )

    @app.route('/turnstile', methods=['GET'])
    async def process_turnstile():
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

        task_id = _new_task('turnstile', url=url, sitekey=sitekey)
        proxy = pick_proxy(config.proxy_support)
        job = lambda page: _turnstile_job(page, url, sitekey, action, cdata)
        asyncio.create_task(_run_solve(task_id, job, config, semaphore, proxy))
        return jsonify({"errorId": 0, "taskId": task_id}), 200

    @app.route('/cf_clearance', methods=['GET'])
    async def process_cf_clearance():
        url = request.args.get('url')
        proxy = request.args.get('proxy')
        timeout_s = request.args.get('timeout', default=60, type=int)

        if not url:
            return jsonify({
                "errorId": 1,
                "errorCode": "ERROR_WRONG_PAGEURL",
                "errorDescription": "The 'url' parameter is required",
            }), 200

        task_id = _new_task('cf_clearance', url=url)
        chosen_proxy = proxy or pick_proxy(config.proxy_support)
        job = lambda page: _cf_clearance_job(page, url, chosen_proxy, timeout_s)
        asyncio.create_task(_run_solve(task_id, job, config, semaphore, chosen_proxy))
        return jsonify({"errorId": 0, "taskId": task_id}), 200

    @app.route('/result', methods=['GET'])
    async def get_result():
        task_id = request.args.get('id')
        task = TASKS.get(task_id) if task_id else None

        if not task:
            return jsonify({
                "errorId": 1,
                "errorCode": "ERROR_WRONG_CAPTCHA_ID",
                "errorDescription": "Invalid task ID/Request parameter",
            }), 200

        if task['status'] == 'processing':
            return jsonify({"status": "processing"}), 200

        if task['status'] == 'fail':
            return jsonify({
                "errorId": 1,
                "errorCode": "ERROR_CAPTCHA_UNSOLVABLE",
                "errorDescription": "Workers could not solve the Captcha",
            }), 200

        result = task['result']
        if task['type'] == 'turnstile':
            solution = {"token": result['token']}
        else:
            solution = result
        return jsonify({"errorId": 0, "status": "ready", "solution": solution}), 200

    @app.route('/')
    async def index():
        return INDEX_HTML

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Turnstile / cf_clearance Solver API")
    parser.add_argument('--no-headless', action='store_true',
                        help='Show browser (default: headless)')
    parser.add_argument('--useragent', type=str,
                        help='Custom User-Agent (headless: default Chrome 150 + sec-ch-ua)')
    parser.add_argument('--debug', action='store_true', help='Debug logging')
    parser.add_argument('--browser_type', type=str, default='chrome',
                        help='chromium, chrome, msedge, camoufox')
    parser.add_argument('--thread', type=int, default=4, help='Max concurrent solves')
    parser.add_argument('--proxy', action='store_true', help='Use proxies.txt')
    parser.add_argument('--host', type=str, default='0.0.0.0')
    parser.add_argument('--port', type=str, default='5072')
    return parser.parse_args()


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


def main() -> None:
    args = parse_args()
    if args.browser_type not in ('chromium', 'chrome', 'msedge', 'camoufox'):
        logger.error(f"Unknown browser type: {args.browser_type}")
        return

    config = BrowserConfig(
        browser_type=args.browser_type,
        headless=not args.no_headless,
        useragent=args.useragent,
        proxy_support=args.proxy,
        debug=args.debug,
    )
    app = create_app(config, threads=args.thread)

    def emergency_shutdown(sig, frame):
        logger.warning("Ctrl+C — shutting down, closing browsers...")
        _kill_child_processes()
        os._exit(0)

    signal.signal(signal.SIGINT, emergency_shutdown)
    signal.signal(signal.SIGTERM, emergency_shutdown)

    try:
        app.run(host=args.host, port=int(args.port))
    except KeyboardInterrupt:
        emergency_shutdown(None, None)


if __name__ == '__main__':
    main()
