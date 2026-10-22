# 🚀 Cloudflare Turnstile & IUAM Automation API

Локальный REST API для автоматизированного прохождения страниц-вызовов Cloudflare Turnstile и IUAM (Under Attack Mode) в реальном браузере — возвращает токены и cf_clearance-сессии.

[![Version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/D3-vin/Turnstile-Solver-NEW/releases)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Educational%20Use-green)](LICENSE)

[![Telegram Channel](https://img.shields.io/badge/Telegram-Канал-blue?logo=telegram)](https://t.me/D3_vin)
[![Telegram Chat](https://img.shields.io/badge/Telegram-Чат-blue?logo=telegram)](https://t.me/D3vin_chat)
[![GitHub](https://img.shields.io/badge/GitHub-Репозиторий-black?logo=github)](https://github.com/D3-vin/Turnstile-Solver-NEW)

[Возможности](#возможности) • [Быстрый старт](#быстрый-старт) • [Использование](#использование) • [API](#api-документация) • [Контакты](#контакты)

[English](README.md) | [Русский](#)

---

> **Новое в 2.0:** поддержка IUAM — прохождение Cloudflare "Under Attack" interstitial и получение `cf_clearance` через новый эндпоинт `/cf_clearance`. Модульная архитектура (`turnstile` / `cf_clearance` / `core`), задачи в памяти, тихие логи.

## Возможности

- 🎯 **Автоматизация Turnstile** - route-intercept заглушка с fallback на реальную страницу, 5-15 секунд на задачу
- 🛡️ **Прохождение IUAM / Challenge** - Managed Challenge + JS Challenge interstitial, получение `cf_clearance` с полным набором для replay (cookies, User-Agent, заголовки)
- 🚀 **Многопоточность** - несколько задач одновременно с лимитом конкуренции
- 🌐 **Несколько браузеров** - Chrome, Edge, Chromium, Camoufox
- 🔌 **Поддержка прокси** - все форматы из `proxies.txt`, плюс прокси на запрос для `/cf_clearance`
- 📊 **REST API** - асинхронная модель задач (создать задачу → опросить результат), легко интегрировать
- 📦 **Без базы данных** - задачи живут в памяти, обслуживание не нужно

---

## Быстрый старт

### 1. Установка

```bash
git clone https://github.com/D3-vin/Turnstile-Solver-NEW.git
cd Turnstile-Solver-NEW
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

### 2. Установка браузера

```bash
python -m patchright install chromium   # или: install msedge / системный Chrome
python -m camoufox fetch                # если нужен Camoufox
```

### 3. Запуск

```bash
python api.py
```

Сервер стартует на `http://0.0.0.0:5072`.

---

## Использование

```bash
python api.py [опции]

Опции:
  --no-headless           Показывать окно браузера (по умолчанию: headless)
  --browser_type string   chromium | chrome | msedge | camoufox (по умолчанию "chrome")
  --thread int            Максимум параллельных задач (по умолчанию 4)
  --proxy                 Использовать случайный прокси из proxies.txt
  --useragent string      Свой User-Agent
  --debug                 Подробные логи + HTTP access-логи
  --host string           Адрес (по умолчанию "0.0.0.0")
  --port string           Порт (по умолчанию "5072")
```

Тестовый клиент:

```bash
python test_solve.py                            # Turnstile (bypass.city)
python test_solve.py --type cf_clearance        # IUAM (ivasms.com)
python test_solve.py --type cf_clearance --proxy http://user:pass@ip:port
```

---

## API-документация

### Turnstile

```
GET /turnstile?url=https://example.com&sitekey=0x4AAAAAAA
```

| Параметр | Тип | Описание | Обязателен |
|----------|-----|----------|------------|
| `url` | string | Страница, на которой валидируется Turnstile | Да |
| `sitekey` | string | Ключ сайта Turnstile | Да |
| `action` | string | Привязка виджета `data-action` | Нет |
| `cdata` | string | Привязка виджета `data-cdata` | Нет |

### IUAM (cf_clearance)

```
GET /cf_clearance?url=https://protected.com&proxy=http://user:pass@ip:port
```

| Параметр | Тип | Описание | Обязателен |
|----------|-----|----------|------------|
| `url` | string | URL страницы под защитой Cloudflare | Да |
| `proxy` | string | Прокси на запрос (cf_clearance привязан к выходному IP) | Нет |
| `timeout` | int | Таймаут задачи, секунды (по умолчанию 60) | Нет |

Оба эндпоинта возвращают задачу:

```json
{ "errorId": 0, "taskId": "d2bcb257-9c37-4f9c-9bc7-1eaee72d96a8" }
```

### Получение результата

```
GET /result?id=d2bcb257-9c37-4f9c-9bc7-1eaee72d96a8
```

В обработке:

```json
{ "status": "processing" }
```

Turnstile готов:

```json
{ "errorId": 0, "status": "ready", "solution": { "token": "0.KBtT-r..." } }
```

cf_clearance готов:

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
    "warning": "cf_clearance привязан к IP + JA3/TLS + User-Agent..."
  }
}
```

> ⚠️ Использовать `cf_clearance` повторно можно только с того же IP, с возвращённым `user_agent` и клиентом с совпадающим TLS-отпечатком (curl-impersonate или реальный браузер).

---

## Структура проекта

```
Turnstile-Solver-NEW/
├── api.py               # Quart-приложение: маршруты, задачи в памяти, CLI
├── test_solve.py        # Тестовый клиент (turnstile / cf_clearance)
├── requirements.txt
├── core/
│   ├── browser.py       # Конфигурация браузера, запуск, контекст, прокси
│   ├── logger.py        # Цветной логгер
│   └── templates.py     # HTML-шаблон Turnstile, JS-сниппеты, route glob
├── turnstile/
│   └── solve.py         # Route-intercept + автоматизация Turnstile на реальной странице
└── cf_clearance/
    └── solve.py         # Прохождение IUAM interstitial + cf_clearance-сессия
```

---

## Решение проблем

### "Browser not found"
Установите браузер: `python -m patchright install chromium` (или `--browser_type chrome` с системным Chrome).

### "Port already in use"
Смените порт: `python api.py --port 5080`.

### cf_clearance not set (челлендж не пройден)
Датацентровские IP оцениваются строго — запустите с `--no-headless` и/или резидентским прокси.

---

## Контакты

- **GitHub**: https://github.com/D3-vin/Turnstile-Solver-NEW
- **Telegram Канал**: [@D3_vin](https://t.me/D3_vin)
- **Telegram Чат**: [@D3vin_chat](https://t.me/D3vin_chat)

---

## Лицензия

Только для образовательных целей — см. файл [LICENSE](LICENSE).

## ⚠️ Отказ от ответственности

ПО предоставляется **исключительно в образовательных и ознакомительных целях**, «как есть» (AS IS), без каких-либо гарантий. Автор не несёт ответственности за любое использование, блокировки API, баны IP и иные последствия — вся ответственность лежит на конечном пользователе. Не аффилировано с Cloudflare, Inc.

> This software is provided for educational and research purposes only, "AS IS". The author is not responsible for any misuse.
