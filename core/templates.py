from typing import Optional
from urllib.parse import urlsplit

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

TOKEN_VALUE_JS = (
    "() => { const e = document.querySelector('[name=cf-turnstile-response]');"
    " return e ? e.value : '' }"
)


def route_glob(url: str) -> str:
    parts = urlsplit(url)
    if parts.path in ('', '/'):
        return f'{parts.scheme}://{parts.netloc}/**'
    return url


def build_route_html(sitekey: str, action: Optional[str] = None,
                     cdata: Optional[str] = None) -> str:
    div = f'<div class="cf-turnstile" data-sitekey="{sitekey}"'
    if action:
        div += f' data-action="{action}"'
    if cdata:
        div += f' data-cdata="{cdata}"'
    return HTML_TEMPLATE.replace('<!--WIDGET-->', div + '></div>')
