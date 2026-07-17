# 🚀 Cloudflare Turnstile + Challenge Solver

Local API solver for Cloudflare Turnstile and IUAM (Under Attack Mode) — harvests tokens and cf_clearance cookies via a real browser.

[![Version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/D3-vin/Turnstile-Solver-NEW/releases)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Educational%20Use-green)](LICENSE)

[![Telegram Channel](https://img.shields.io/badge/Telegram-Channel-blue?logo=telegram)](https://t.me/D3_vin)
[![Telegram Chat](https://img.shields.io/badge/Telegram-Chat-blue?logo=telegram)](https://t.me/D3vin_chat)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-black?logo=github)](https://github.com/D3-vin/Turnstile-Solver-NEW)

[Features](#features) • [Quick Start](#quick-start) • [Usage](#usage) • [API](#api-documentation) • [Contact](#contact)

[English](#) | [Русский](README_RU.md)

---

> **New in 2.0:** IUAM support — pass Cloudflare "Under Attack" interstitials and harvest `cf_clearance` via the new `/cf_clearance` endpoint. Modular architecture (`turnstile` / `cf_clearance` / `core`), in-memory task storage, quiet logs.

## Features

- 🎯 **Turnstile solving** - Route-intercept stub page with real-page fallback, 5-15 seconds per solve
- 🛡️ **IUAM / Challenge pass** - Managed Challenge + JS Challenge interstitials, harvests `cf_clearance` with the full replay bundle (cookies, User-Agent, headers)
- 🚀 **Multi-threaded** - Solve multiple tasks simultaneously with a concurrency limit
- 🌐 **Multiple browsers** - Chrome, Edge, Chromium, Camoufox
- 🔌 **Proxy support** - All formats from `proxies.txt`, plus per-request proxy for `/cf_clearance`
- 📊 **REST API** - Async task model (create task → poll result), easy to integrate
- 📦 **No database** - Tasks live in memory, nothing to maintain

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/D3-vin/Turnstile-Solver-NEW.git
cd Turnstile-Solver-NEW
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

### 2. Install a browser

```bash
python -m patchright install chromium   # or: install msedge / use system Chrome
python -m camoufox fetch                # if you want Camoufox
```

### 3. Run

```bash
python api.py
```

Server starts on `http://0.0.0.0:5072`.

---

## Usage

```bash
python api.py [options]

Options:
  --no-headless           Show the browser window (default: headless)
  --browser_type string   chromium | chrome | msedge | camoufox (default "chrome")
  --thread int            Max concurrent solves (default 4)
  --proxy                 Use random proxy from proxies.txt
  --useragent string      Custom User-Agent
  --debug                 Verbose logging + HTTP access logs
  --host string           Listen address (default "0.0.0.0")
  --port string           Listen port (default "5072")
```

Test client:

```bash
python test_solve.py                            # Turnstile (bypass.city)
python test_solve.py --type cf_clearance        # IUAM (ivasms.com)
python test_solve.py --type cf_clearance --proxy http://user:pass@ip:port
```

---

## API Documentation

### Solve Turnstile

```
GET /turnstile?url=https://example.com&sitekey=0x4AAAAAAA
```

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `url` | string | Page where Turnstile is validated | Yes |
| `sitekey` | string | Turnstile site key | Yes |
| `action` | string | Widget `data-action` binding | No |
| `cdata` | string | Widget `data-cdata` binding | No |

### Pass IUAM (cf_clearance)

```
GET /cf_clearance?url=https://protected.com&proxy=http://user:pass@ip:port
```

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `url` | string | Cloudflare-protected page URL | Yes |
| `proxy` | string | Per-request proxy (cf_clearance is bound to the exit IP) | No |
| `timeout` | int | Solve timeout, seconds (default 60) | No |

Both endpoints return a task:

```json
{ "errorId": 0, "taskId": "d2cbb257-9c37-4f9c-9bc7-1eaee72d96a8" }
```

### Get Result

```
GET /result?id=d2cbb257-9c37-4f9c-9bc7-1eaee72d96a8
```

Processing:

```json
{ "status": "processing" }
```

Turnstile ready:

```json
{ "errorId": 0, "status": "ready", "solution": { "token": "0.KBtT-r..." } }
```

cf_clearance ready:

```json
{
  "errorId": 0,
  "status": "ready",
  "solution": {
    "cf_clearance": { "name": "cf_clearance", "value": "...", "domain": ".example.com" },
    "cookies": [ "..." ],
    "user_agent": "Mozilla/5.0 ...",
    "headers": { "User-Agent": "...", "Accept-Language": "..." },
    "proxy": "http://...",
    "warning": "cf_clearance is bound to IP + JA3/TLS + User-Agent..."
  }
}
```

> ⚠️ Replay `cf_clearance` only from the same IP, with the returned `user_agent`, over a client with a matching TLS fingerprint (curl-impersonate or a real browser).

---

## Project Structure

```
Turnstile-Solver-NEW/
├── api.py               # Quart app: routes, in-memory tasks, CLI
├── test_solve.py        # Test client (turnstile / cf_clearance)
├── requirements.txt
├── core/
│   ├── browser.py       # Browser config, launch, context, proxy helpers
│   ├── logger.py        # Colored logger
│   └── templates.py     # Turnstile HTML template, JS snippets, route glob
├── turnstile/
│   └── solve.py         # Route-intercept + real-page Turnstile solving
└── cf_clearance/
    └── solve.py         # IUAM interstitial pass + cf_clearance harvest
```

---

## Troubleshooting

### "Browser not found"
Install the browser: `python -m patchright install chromium` (or use `--browser_type chrome` with system Chrome).

### "Port already in use"
Change it: `python api.py --port 5080`.

### cf_clearance not set (challenge unsolved)
Datacenter IPs are scored harshly — run with `--no-headless` and/or a residential proxy.

---

## Contact

- **GitHub**: https://github.com/D3-vin/Turnstile-Solver-NEW
- **Telegram Channel**: [@D3_vin](https://t.me/D3_vin)
- **Telegram Chat**: [@D3vin_chat](https://t.me/D3vin_chat)

### ❤️ Support the Project

- **EVM:** 0xeba21af63e707ce84b76a87d0ba82140048c057e (ETH, BNB, etc)
- **TRON:** TEfECnyz5G1EkFrUqnbFcWLVdLvAgW9Raa
- **TON:** UQCJ7KC2zxV_zKwLahaHf9jxy0vsWRcvQFie_FUBJW-9LcEW
- **BTC:** bc1qdag98y5yahs6wf7rsfeh4cadsjfzmn5ngpjrcf
- **SOL:** EwXXR4VqmWSNz1sjhZ8qcQ882i4URwAwhixSPEbDzyv6
- **SUI:** 0x76da9b74c61508fbbd0b3e1989446e036b0622f252dd8d07c3fce759b239b47d

---

## License

Educational use only - see [LICENSE](LICENSE) file.

**⚠️ Disclaimer**: This tool is for educational purposes only. Use at your own risk. The author is not responsible for API blocking, IP bans, or any other consequences.
