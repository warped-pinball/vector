"""Generate static HTTP API documentation for backend routes.

This script statically parses ``src/common/backend.py`` using ``ast`` and writes
HTML documentation to the ``docs`` directory. It avoids importing any
MicroPython-specific modules so it can run in standard CPython.
"""
from __future__ import annotations

import ast
import html
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = REPO_ROOT / "src" / "common" / "backend.py"
DOCS_DIR = REPO_ROOT / "docs"
REPO_URL = "https://github.com/warped-pinball/vector"
WARP_URL = "https://warpedpinball.com"
DEMO_URL = "https://vector.doze.dev"


class RouteDoc:
    def __init__(
        self,
        path: str,
        handler: str,
        lineno: int,
        auth: bool = False,
        cool_down_seconds: int = 0,
        single_instance: bool = False,
        docstring: Optional[str] = None,
    ) -> None:
        self.path = path
        self.handler = handler
        self.lineno = lineno
        self.auth = auth
        self.cool_down_seconds = cool_down_seconds
        self.single_instance = single_instance
        self.docstring = docstring
        self.doc_block: Dict[str, Any] | None = None
        self.inferred_fields = {
            "query": set(),
            "body": set(),
            "headers": set(),
        }


# --- Docstring parsing ----------------------------------------------------


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        # Reject integer-like values with leading zeros (e.g. "0123"),
        # but allow "0" and non-integer values like "0.5".
        if value.startswith("0") and len(value) > 1 and value.isdigit():
            raise ValueError
        return int(value)
    except (ValueError, OverflowError):
        pass
    try:
        return float(value)
    except (ValueError, OverflowError):
        return value


def parse_structured_docstring(docstring: str) -> Optional[Dict[str, Any]]:
    """Parse the optional @api ... @end block from a docstring."""

    if not docstring:
        return None

    lines = docstring.splitlines()
    start = None
    end = None
    for idx, line in enumerate(lines):
        if line.strip().startswith("@api"):
            start = idx + 1
        if line.strip().startswith("@end"):
            end = idx
            break
    if start is None or end is None or start >= end:
        return None

    block_lines = lines[start:end]

    root: Dict[str, Any] = {}
    stack: List[Dict[str, Any]] = [
        {"indent": -1, "container": root, "parent": None, "key": None}
    ]

    def current_container(indent: int):
        while stack and indent <= stack[-1]["indent"]:
            stack.pop()
        return stack[-1]

    idx = 0
    while idx < len(block_lines):
        raw_line = block_lines[idx]
        if not raw_line.strip() or raw_line.strip().startswith("#"):
            idx += 1
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        entry = current_container(indent)
        container = entry["container"]
        line = raw_line.strip()

        if line.startswith("- "):
            item_line = line[2:].strip()
            if not isinstance(container, list):
                if isinstance(container, dict) and entry["parent"] is not None:
                    new_list: List[Any] = []
                    entry["parent"][entry["key"]] = new_list
                    entry["container"] = new_list
                    container = new_list
                else:
                    return None
            if ":" in item_line:
                key, value = item_line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if value:
                    item: Dict[str, Any] = {key: parse_scalar(value)}
                    container.append(item)
                    stack.append(
                        {
                            "indent": indent,
                            "container": item,
                            "parent": container,
                            "key": None,
                        }
                    )
                else:
                    new_container: Dict[str, Any] = {}
                    item = {key: new_container}
                    container.append(item)
                    stack.append(
                        {
                            "indent": indent,
                            "container": new_container,
                            "parent": item,
                            "key": key,
                        }
                    )
            else:
                container.append(parse_scalar(item_line))
            idx += 1
            continue

        if ":" not in line:
            idx += 1
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        parent_container = container
        if isinstance(parent_container, list):
            if not parent_container or not isinstance(parent_container[-1], dict):
                parent_container.append({})
            parent_container = parent_container[-1]

        if key == "example" and (not value or value.startswith(("{", "["))):
            collected: List[str] = []
            if value:
                collected.append(value)
            look_ahead = idx + 1
            while look_ahead < len(block_lines):
                next_line = block_lines[look_ahead]
                if not next_line.strip():
                    collected.append("")
                    look_ahead += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip(" "))
                if next_indent <= indent:
                    break
                collected.append(next_line.rstrip("\n"))
                look_ahead += 1

            if collected:
                # Remove any common leading whitespace so nested structures keep their relative
                # indentation while still fitting nicely in the rendered <pre> blocks.
                parent_container[key] = textwrap.dedent("\n".join(collected)).strip("\n")
            else:
                parent_container[key] = ""
            idx = look_ahead
            continue

        if value:
            parent_container[key] = parse_scalar(value)
            idx += 1
        else:
            new_container: Dict[str, Any] = {}
            parent_container[key] = new_container
            stack.append(
                {
                    "indent": indent,
                    "container": new_container,
                    "parent": parent_container,
                    "key": key,
                }
            )
            idx += 1

    return root


# --- AST parsing ----------------------------------------------------------


def extract_routes() -> List[RouteDoc]:
    source = BACKEND_PATH.read_text()
    tree = ast.parse(source)
    routes: List[RouteDoc] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        route_info = None
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and getattr(dec.func, "id", None) == "add_route":
                if not dec.args:
                    continue
                path_arg = dec.args[0]
                if not isinstance(path_arg, ast.Constant) or not isinstance(
                    path_arg.value, str
                ):
                    continue
                path = path_arg.value
                kwargs = {k.arg: k.value for k in dec.keywords}
                route_info = (
                    path,
                    bool(
                        ast.literal_eval(kwargs.get("auth", ast.Constant(False)))
                        if kwargs.get("auth") is not None
                        else False
                    ),
                    int(
                        ast.literal_eval(
                            kwargs.get("cool_down_seconds", ast.Constant(0))
                        )
                    ),
                    bool(
                        ast.literal_eval(
                            kwargs.get("single_instance", ast.Constant(False))
                        )
                    ),
                )
                break
        if not route_info:
            continue

        path, auth, cool_down_seconds, single_instance = route_info
        docstring = ast.get_docstring(node)
        rd = RouteDoc(
            path=path,
            handler=node.name,
            lineno=node.lineno,
            auth=auth,
            cool_down_seconds=cool_down_seconds,
            single_instance=single_instance,
            docstring=docstring,
        )
        rd.doc_block = parse_structured_docstring(docstring or "")
        infer_request_fields(node, rd)
        routes.append(rd)

    routes.sort(key=lambda r: r.lineno)
    return routes


def _is_request_attr(node: ast.AST, attr_name: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attr_name
        and isinstance(node.value, ast.Name)
        and node.value.id == "request"
    )


def _extract_key_from_subscript(node: ast.Subscript) -> Optional[str]:
    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return None


def infer_request_fields(func_node: ast.FunctionDef, route: RouteDoc) -> None:
    for node in ast.walk(func_node):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            attr = node.value
            key = _extract_key_from_subscript(node)
            if not key:
                continue
            if _is_request_attr(attr, "data") or _is_request_attr(attr, "json"):
                route.inferred_fields["body"].add(key)
            elif _is_request_attr(attr, "args"):
                route.inferred_fields["query"].add(key)
            elif _is_request_attr(attr, "headers"):
                route.inferred_fields["headers"].add(key)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            func_attr = node.func
            if not node.args:
                continue
            first_arg = node.args[0]
            if not isinstance(first_arg, ast.Constant) or not isinstance(
                first_arg.value, str
            ):
                continue
            key = first_arg.value
            if _is_request_attr(func_attr, "args"):
                route.inferred_fields["query"].add(key)
            elif _is_request_attr(func_attr, "headers"):
                route.inferred_fields["headers"].add(key)
            elif _is_request_attr(func_attr, "data") or _is_request_attr(
                func_attr, "json"
            ):
                route.inferred_fields["body"].add(key)


# --- HTML rendering -------------------------------------------------------


def render_request_fields(route: RouteDoc) -> str:
    doc_req = (route.doc_block or {}).get("request", {}) if route.doc_block else {}
    sections = ["query", "body", "headers"]
    html_parts: List[str] = []
    for section in sections:
        entries: List[str] = []
        if doc_req and section in doc_req:
            for item in doc_req.get(section, []):
                if isinstance(item, dict):
                    name = html.escape(str(item.get("name", "")))
                    desc = html.escape(str(item.get("description", "")))
                    typ = html.escape(str(item.get("type", "")))
                    req = "required" if item.get("required") else "optional"
                    entries.append(f"<li><code>{name}</code> ({typ}, {req}) - {desc}</li>")
        else:
            inferred = sorted(route.inferred_fields.get(section, []))
            for key in inferred:
                entries.append(f"<li><code>{html.escape(key)}</code> (inferred)</li>")
        if entries:
            html_parts.append(
                f"<h4>{section.title()} parameters</h4><ul>{''.join(entries)}</ul>"
            )
    return "".join(html_parts)


def render_response(route: RouteDoc) -> str:
    if route.doc_block and "response" in route.doc_block:
        resp = route.doc_block["response"]
        parts = []
        if isinstance(resp, dict):
            if "status_codes" in resp:
                sc_list = resp.get("status_codes", [])
                status_html = "".join(
                    f"<li><code>{html.escape(str(item.get('code')))}</code> - {html.escape(str(item.get('description', '')))}</li>"
                    for item in sc_list
                    if isinstance(item, dict)
                )
                if status_html:
                    parts.append(f"<h4>Status Codes</h4><ul>{status_html}</ul>")
            if "body" in resp:
                body = resp["body"]
                if isinstance(body, dict):
                    body_desc = html.escape(str(body.get("description", "")))
                    example = body.get("example")
                    parts.append(f"<p><strong>Response body:</strong> {body_desc}</p>")
                    if example is not None:
                        parts.append(
                            f"<pre><code>{html.escape(str(example))}</code></pre>"
                        )
        if parts:
            return "".join(parts)
    return "<p>No structured response documented.</p>"


def render_route(route: RouteDoc) -> str:
    doc = route.doc_block or {}
    summary = html.escape(str(doc.get("summary", ""))) if doc else ""
    description = summary or "No description provided."
    handler_link = (
        f"<a href='{REPO_URL}/blob/main/src/common/backend.py#L{route.lineno}'"
        f" target='_blank' rel='noopener noreferrer'>{html.escape(route.handler)}</a>"
    )
    auth_note = (
        "<p><strong>Authentication:</strong> Required – see <a href='authentication.html'>authentication guide</a>.</p>"
        if route.auth
        else ""
    )
    cooldown_note = (
        f"<p><strong>Cooldown:</strong> {route.cool_down_seconds}s</p>"
        if route.cool_down_seconds
        else ""
    )
    single_note = "<p><strong>Single instance:</strong> Yes</p>" if route.single_instance else ""

    request_fields = render_request_fields(route)
    response_block = render_response(route)

    description_block = ""
    if doc:
        desc_lines = []
        if "summary" in doc:
            desc_lines.append(f"<p>{html.escape(str(doc.get('summary')))}</p>")
        extra_desc = doc.get("description")
        if extra_desc:
            desc_lines.append(f"<p>{html.escape(str(extra_desc))}</p>")
        description_block = "".join(desc_lines)
    else:
        description_block = f"<p>{description}</p>"

    anchor = html.escape(route.path.strip("/").replace("/", "-")) or "root"

    return f"""
    <section id="{anchor}">
      <h2><code>{html.escape(route.path)}</code></h2>
      <p><strong>Handler:</strong> {handler_link}</p>
      {auth_note}{cooldown_note}{single_note}
      {description_block}
      <h3>Request</h3>
      {request_fields or '<p>No parameters inferred.</p>'}
      <h3>Response</h3>
      {response_block}
    </section>
    """


def render_index(routes: List[RouteDoc]) -> str:
    items = "".join(
        f"<li><a href='#" + html.escape(r.path.strip('/').replace('/', '-') or 'root') + "'>" + html.escape(r.path) + "</a></li>"
        for r in routes
    )
    return f"<ul class=\"endpoint-list\">{items}</ul>"


def build_html(routes: List[RouteDoc]) -> str:
    sections = "".join(render_route(r) for r in routes)
    index = render_index(routes)
    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Vector HTTP API</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0d1117;
      --panel: #111827;
      --panel-border: #1f2937;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --accent: #38bdf8;
      --code-bg: #0b1221;
      --code-text: #f8fafc;
      --code-border: #1d2a3f;
      --shadow: 0 10px 30px rgba(0,0,0,0.35);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
      margin: 0 auto;
      padding: 0 1.5rem 3rem;
      max-width: 1100px;
      color: var(--text);
      background: radial-gradient(circle at 20% 20%, rgba(56, 189, 248, 0.08), transparent 25%),
                  radial-gradient(circle at 80% 0%, rgba(14, 165, 233, 0.08), transparent 25%),
                  var(--bg);
    }}
    h1, h2, h3 {{ color: var(--text); margin-top: 0; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 14px;
      padding: 1.5rem;
      box-shadow: var(--shadow);
      margin-bottom: 1.75rem;
    }}
    .panel section {{ border-bottom: 1px solid var(--panel-border); padding-bottom: 1.25rem; margin-bottom: 1.5rem; }}
    ul {{ list-style: none; padding-left: 0; }}
    ul li {{ margin: 0.3rem 0; }}
    .endpoint-list a {{ font-weight: 600; }}
    code {{ background: var(--code-bg); color: var(--code-text); padding: 2px 6px; border-radius: 6px; border: 1px solid var(--code-border); }}
    pre {{
      background: var(--code-bg);
      color: var(--code-text);
      padding: 1rem;
      border-radius: 12px;
      border: 1px solid var(--code-border);
      overflow-x: auto;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02);
    }}
    pre code {{ display: block; font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace; font-size: 0.95rem; line-height: 1.5; }}
    .meta {{ color: var(--muted); font-size: 0.95rem; margin: 0.35rem 0; }}
    .tag {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.85rem; border: 1px solid var(--panel-border); background: rgba(56,189,248,0.1); color: var(--accent); }}
    .topbar {{
      position: sticky;
      top: 0;
      backdrop-filter: blur(12px);
      background: rgba(13,17,23,0.9);
      border-bottom: 1px solid var(--panel-border);
      padding: 1rem 0;
      margin-bottom: 1rem;
      z-index: 20;
    }}
    .topbar .nav {{ display: flex; flex-wrap: wrap; gap: 0.65rem; align-items: center; justify-content: space-between; }}
    .topbar .nav-links {{ display: flex; flex-wrap: wrap; gap: 0.65rem; align-items: center; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.35rem 0.8rem;
      border-radius: 999px;
      border: 1px solid var(--panel-border);
      background: rgba(56,189,248,0.08);
      color: var(--text);
      font-weight: 600;
      box-shadow: var(--shadow);
    }}
    .badge {{ display: inline-flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; }}
    .hero {{ display: grid; gap: 0.8rem; }}
    .card-grid {{ display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }}
    .card {{ padding: 1rem; border-radius: 12px; border: 1px solid var(--panel-border); background: rgba(255,255,255,0.02); box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02); height: 100%; }}
    .card h3 {{ margin-top: 0; }}
    .cta {{ display: inline-flex; align-items: center; gap: 0.35rem; margin-top: 0.5rem; font-weight: 600; }}
    .toc-list {{ padding-left: 1rem; list-style: disc; color: var(--text); }}
    .toc-list li {{ margin: 0.25rem 0; }}
    .spacer {{ flex: 1 1 auto; }}
    .back-top {{ text-align: right; margin-top: 1rem; }}
  </style>
</head>
<body>
  <a id=\"top\"></a>
  <header class=\"topbar\">
    <div class=\"nav\">
      <div class=\"badge\">
        <strong>Vector HTTP API</strong>
        <a class=\"pill\" href=\"{REPO_URL}/releases/latest\" target=\"_blank\" rel=\"noopener noreferrer\">Release badge</a>
        <img alt=\"Latest release\" src=\"https://img.shields.io/github/v/release/warped-pinball/vector?label=release\" />
        <img alt=\"Last commit\" src=\"https://img.shields.io/github/last-commit/warped-pinball/vector?label=updated\" />
      </div>
      <div class=\"nav-links\">
        <a class=\"pill\" href=\"#toc\">Table of contents</a>
        <a class=\"pill\" href=\"{REPO_URL}\" target=\"_blank\" rel=\"noopener noreferrer\">Main repository</a>
        <a class=\"pill\" href=\"{WARP_URL}\" target=\"_blank\" rel=\"noopener noreferrer\">WarpedPinball.com</a>
        <a class=\"pill\" href=\"{DEMO_URL}\" target=\"_blank\" rel=\"noopener noreferrer\">Live demo</a>
        <a class=\"pill\" href=\"#top\">Back to top</a>
      </div>
    </div>
  </header>
  <main>
    <div class=\"panel hero\">
      <div>
        <h1>Vector HTTP API</h1>
        <p class=\"meta\">Generated automatically from <code>src/common/backend.py</code>. Use this page as the landing pad for connectivity guides and endpoint documentation.</p>
      </div>
      <div class=\"meta\">
        <span class=\"tag\">Statically generated</span>
        <span class=\"tag\">MicroPython friendly</span>
      </div>
      <p class=\"meta\">Need authentication details? Visit the <a href=\"authentication.html\">Authentication guide</a>.</p>
    </div>

    <div class=\"panel\" id=\"toc\">
      <h2>Table of contents</h2>
      <ul class=\"toc-list\">
        <li><a href=\"#connectivity\">Connectivity guides</a></li>
        <li><a href=\"#routes\">Routes &amp; endpoints</a></li>
      </ul>
    </div>

    <div class=\"panel\" id=\"connectivity\">
      <h2>Connectivity guides</h2>
      <div class=\"card-grid\">
        <div class=\"card\">
          <h3>HTTP over the network</h3>
          <p class=\"meta\">How to reach your Vector board over WiFi, including TLS notes and curl examples.</p>
          <a class=\"cta\" href=\"network.html\">Open network guide →</a>
        </div>
        <div class=\"card\">
          <h3>Peer discovery</h3>
          <p class=\"meta\">Broadcasts, HELLO/FULL frames, and a ready-to-run desktop script.</p>
          <a class=\"cta\" href=\"discovery.html\">Open discovery guide →</a>
        </div>
        <div class=\"card\">
          <h3>USB transport</h3>
          <p class=\"meta\">Serial framing, escaping pipes, and a host-side client to speak to the device.</p>
          <a class=\"cta\" href=\"usb.html\">Open USB guide →</a>
        </div>
        <div class=\"card\">
          <h3>Authentication</h3>
          <p class=\"meta\">Login flow, JSON payloads, and how to attach session cookies to API calls.</p>
          <a class=\"cta\" href=\"authentication.html\">Open authentication guide →</a>
        </div>
      </div>
    </div>

    <div class=\"panel\" id=\"routes\">
      <div class=\"nav\" style=\"gap: 0.5rem; align-items: baseline;\">
        <h2 style=\"margin: 0;\">Routes &amp; endpoints</h2>
        <div class=\"spacer\"></div>
        <a class=\"pill\" href=\"#top\">Back to top</a>
      </div>
      <p class=\"meta\">Jump directly to a handler. Links open source on GitHub with accurate line numbers.</p>
      <div class=\"endpoint-list\">{index}</div>
    </div>

    <div class=\"panel\">{sections}<p class=\"back-top\"><a href=\"#toc\">↑ Back to table of contents</a></p></div>
  </main>
</body>
</html>
"""


def build_authentication_html() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vector HTTP API Authentication</title>
  <style>
    body { font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif; max-width: 960px; margin: 2.5rem auto; padding: 0 1.5rem 3rem; color: #e5e7eb; background: #0d1117; }
    h1, h2, h3 { color: #e5e7eb; }
    a { color: #38bdf8; text-decoration: none; }
    a:hover { text-decoration: underline; }
    code { background: #0b1221; color: #f8fafc; padding: 2px 6px; border-radius: 6px; border: 1px solid #1d2a3f; }
    pre { background: #0b1221; color: #f8fafc; padding: 1rem; border-radius: 12px; border: 1px solid #1d2a3f; overflow-x: auto; }
    pre code { display: block; font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace; line-height: 1.5; }
    .panel { background: #111827; border: 1px solid #1f2937; border-radius: 14px; padding: 1.5rem; box-shadow: 0 10px 30px rgba(0,0,0,0.35); margin-bottom: 1.75rem; }
    ol { padding-left: 1.25rem; }
  </style>
</head>
<body>
  <h1>Authentication</h1>
  <div class="panel">
    <p>Authenticated routes require an HMAC signature tied to a one-time challenge token. Use this flow for any route marked as requiring authentication.</p>
  </div>
  <div class="panel">
    <h2>Flow</h2>
    <ol>
      <li>Call <code>/api/auth/challenge</code> to receive a hexadecimal <code>challenge</code> string.</li>
      <li>Build the message string by concatenating <code>challenge + request_path + raw_body</code>. If the request has no body, use an empty string for <code>raw_body</code>.</li>
      <li>Compute the HMAC-SHA256 digest of the message using the configured password as the key.</li>
      <li>Send the protected request with headers <code>x-auth-challenge</code> (the issued token) and <code>x-auth-hmac</code> (the hexadecimal digest).</li>
      <li>Challenges expire after 60 seconds and are removed once successfully used. Request a new challenge if you receive an expiration or invalid challenge error.</li>
    </ol>
  </div>
  <div class="panel">
    <h2>Examples</h2>
    <p>Example message construction for <code>/api/settings/set_show_ip</code> without a request body:</p>
    <pre><code>challenge = "deadbeef..."  # obtained from /api/auth/challenge
path = "/api/settings/set_show_ip"
body = ""  # no payload for this route
message = challenge + path + body</code></pre>
    <p>Include the generated <code>x-auth-challenge</code> and <code>x-auth-hmac</code> headers in the subsequent request.</p>
  </div>
  <div class="panel">
    <h2>Ready-to-run Python example</h2>
    <p>This script retrieves a challenge, signs a protected request, and prints the response. Save it locally and run with <code>python auth_demo.py</code>.</p>
<pre><code>#!/usr/bin/env python3
import hashlib
import hmac
import requests

BASE_URL = "http://192.168.1.42"  # replace with your board IP
PASSWORD = "your-password"         # the device password used for HMAC


def signed_get(path: str):
    challenge = requests.get(f"{BASE_URL}/api/auth/challenge", timeout=5).json()["challenge"]
    message = (challenge + path).encode()
    signature = hmac.new(PASSWORD.encode(), message, hashlib.sha256).hexdigest()

    return requests.get(
        f"{BASE_URL}{path}",
        headers={
            "x-auth-challenge": challenge,
            "x-auth-hmac": signature,
        },
        timeout=5,
    )


if __name__ == "__main__":
    print("Version:", requests.get(f"{BASE_URL}/api/version", timeout=5).json())
    resp = signed_get("/api/settings/set_show_ip")
    print("Authenticated response:", resp.status_code, resp.text)
</code></pre>
    <p>Swap <code>BASE_URL</code> and <code>PASSWORD</code> for your device. Reuse <code>signed_get</code> for any authenticated route.</p>
  </div>
  <p><a href="index.html">Back to API reference</a></p>
</body>
</html>
"""


def build_network_html() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vector HTTP API over the network</title>
  <style>
    body { font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif; max-width: 960px; margin: 2.5rem auto; padding: 0 1.5rem 3rem; color: #e5e7eb; background: #0d1117; }
    h1, h2, h3 { color: #e5e7eb; }
    a { color: #38bdf8; text-decoration: none; }
    a:hover { text-decoration: underline; }
    code { background: #0b1221; color: #f8fafc; padding: 2px 6px; border-radius: 6px; border: 1px solid #1d2a3f; }
    pre { background: #0b1221; color: #f8fafc; padding: 1rem; border-radius: 12px; border: 1px solid #1d2a3f; overflow-x: auto; }
    pre code { display: block; font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace; line-height: 1.5; }
    .panel { background: #111827; border: 1px solid #1f2937; border-radius: 14px; padding: 1.5rem; box-shadow: 0 10px 30px rgba(0,0,0,0.35); margin-bottom: 1.75rem; }
    ol { padding-left: 1.25rem; }
  </style>
</head>
<body>
  <h1>Accessing the API over the network</h1>
  <div class="panel">
    <p>Use regular HTTP requests against the board's IP address (e.g. <code>http://192.168.1.42</code>). All routes are GET endpoints unless otherwise documented.</p>
    <p>For routes marked as authenticated, obtain an HMAC challenge token first and include the required headers; see <a href="authentication.html">Authentication</a> for the signing flow.</p>
  </div>
  <div class="panel">
    <h2>Quick demo script</h2>
    <p>The snippet below discovers the firmware version and, if needed, signs an authenticated request using the standard challenge flow.</p>
<pre><code>import hashlib
import hmac
import requests

BASE_URL = "http://192.168.1.42"
PASSWORD = "your-password"

def get(path):
    return requests.get(BASE_URL + path, timeout=5)

print("Version:", get("/api/version").json())

# Authenticated example: toggle show_ip
challenge = get("/api/auth/challenge").json()["challenge"]
path = "/api/settings/set_show_ip"
body = ""  # no body for this GET route
message = (challenge + path + body).encode()
signature = hmac.new(PASSWORD.encode(), message, hashlib.sha256).hexdigest()

resp = requests.get(
    BASE_URL + path,
    headers={
        "x-auth-challenge": challenge,
        "x-auth-hmac": signature,
    },
    timeout=5,
)
print("show_ip response:", resp.text)
</code></pre>
    <p>Swap <code>BASE_URL</code> for your board's address and reuse the helper to call other authenticated routes.</p>
  </div>
  <p><a href="index.html">Back to API reference</a></p>
</body>
</html>
"""


def build_discovery_html() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Discover boards on the network</title>
  <style>
    body { font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif; max-width: 960px; margin: 2.5rem auto; padding: 0 1.5rem 3rem; color: #e5e7eb; background: #0d1117; }
    h1, h2, h3 { color: #e5e7eb; }
    a { color: #38bdf8; text-decoration: none; }
    a:hover { text-decoration: underline; }
    code { background: #0b1221; color: #f8fafc; padding: 2px 6px; border-radius: 6px; border: 1px solid #1d2a3f; }
    pre { background: #0b1221; color: #f8fafc; padding: 1rem; border-radius: 12px; border: 1px solid #1d2a3f; overflow-x: auto; }
    pre code { display: block; font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace; line-height: 1.5; }
    .panel { background: #111827; border: 1px solid #1f2937; border-radius: 14px; padding: 1.5rem; box-shadow: 0 10px 30px rgba(0,0,0,0.35); margin-bottom: 1.75rem; }
    ol { padding-left: 1.25rem; }
  </style>
</head>
<body>
  <h1>Discover boards on the network</h1>
  <div class="panel">
    <p>The discovery helpers in <code>src/common/discovery.py</code> broadcast a small UDP heartbeat on port <code>37020</code>. Boards elect the lowest IP as the registry device, which replies with the full peer list.</p>
    <p>On a laptop or desktop you will need to implement the wire protocol yourself (you cannot import the MicroPython helpers directly). The script below mirrors the on-device behavior using standard Python sockets.</p>
  </div>
  <div class="panel">
    <h2>Quick start</h2>
    <ol>
      <li>Broadcast a HELLO frame (<code>[1, name_length, name bytes]</code>) on UDP port <code>37020</code>.</li>
      <li>Listen for FULL responses (<code>[2, count, ip bytes..., name length, name bytes]</code>) from the elected registry node.</li>
      <li>Parse the peer map from the FULL payload and refresh it periodically.</li>
    </ol>
    <p>Ready-to-run desktop script:</p>
<pre><code>#!/usr/bin/env python3
import socket
import time

DISCOVERY_PORT = 37020
NAME = "DesktopClient"


def send_hello(sock: socket.socket):
    name_bytes = NAME.encode("utf-8")[:32]
    payload = bytes([1, len(name_bytes)]) + name_bytes
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.sendto(payload, ("255.255.255.255", DISCOVERY_PORT))


def decode_full(data: bytes):
    peers = {}
    if len(data) < 2 or data[0] != 2:
        return peers
    count = data[1]
    offset = 2
    for _ in range(count):
        if len(data) < offset + 5:
            break
        ip_bytes = data[offset : offset + 4]
        offset += 4
        name_len = data[offset]
        offset += 1
        name = data[offset : offset + name_len].decode("utf-8", "ignore")
        offset += name_len
        ip_str = socket.inet_ntoa(ip_bytes)
        peers[ip_str] = name
    return peers


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", DISCOVERY_PORT))
    send_hello(sock)
    print("Broadcasted discovery HELLO... listening for peers")

    while True:
        sock.settimeout(5)
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            send_hello(sock)
            continue

        peers = decode_full(data)
        if peers:
            print(f"Registry {addr[0]} reports peers: {peers}")


if __name__ == "__main__":
    main()
</code></pre>
    <p>Run the script on the same network as the boards. It will rebroadcast a HELLO every few seconds if no responses arrive.</p>
  </div>
  <p><a href="index.html">Back to API reference</a></p>
</body>
</html>
"""


def build_usb_html() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Accessing the API over USB</title>
  <style>
    body { font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif; max-width: 960px; margin: 2.5rem auto; padding: 0 1.5rem 3rem; color: #e5e7eb; background: #0d1117; }
    h1, h2, h3 { color: #e5e7eb; }
    a { color: #38bdf8; text-decoration: none; }
    a:hover { text-decoration: underline; }
    code { background: #0b1221; color: #f8fafc; padding: 2px 6px; border-radius: 6px; border: 1px solid #1d2a3f; }
    pre { background: #0b1221; color: #f8fafc; padding: 1rem; border-radius: 12px; border: 1px solid #1d2a3f; overflow-x: auto; }
    pre code { display: block; font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace; line-height: 1.5; }
    .panel { background: #111827; border: 1px solid #1f2937; border-radius: 14px; padding: 1.5rem; box-shadow: 0 10px 30px rgba(0,0,0,0.35); margin-bottom: 1.75rem; }
    ol { padding-left: 1.25rem; }
  </style>
</head>
<body>
  <h1>Accessing the API over USB</h1>
  <div class="panel">
    <p>The USB transport reuses the same route handlers via <code>src/common/usb_comms.py</code>. Requests are read from the serial console as <code>route|headers|body</code> lines and responded to with JSON.</p>
    <p>Host-side scripts cannot import the MicroPython modules. Use the standalone client below based on <code>dev/usb_coms_demo.py</code> to talk to the board over serial.</p>
  </div>
  <div class="panel">
    <h2>Frame format</h2>
    <p>Each request line contains three pipe-delimited fields. Escape literal pipes in headers or body as <code>\|</code>. Headers are provided as raw HTTP-style text (e.g. <code>Content-Type: application/json</code> on separate lines) and the body is optional.</p>
  </div>
  <div class="panel">
    <h2>Host demo snippet</h2>
    <p>Save the following as <code>usb_client.py</code> (adapted from <code>dev/usb_coms_demo.py</code>) and run it locally:</p>
<pre><code>#!/usr/bin/env python3
import json
import time

import serial


def send_and_receive(port: str, route: str, headers=None, body_text=""):
    ser = serial.Serial(port=port, baudrate=115200, timeout=10)
    time.sleep(2)  # allow the device to reset
    headers = headers or {"Content-Type": "application/json"}
    header_text = "\\n".join(f"{k}: {v}" for k, v in headers.items())
    frame = f"{route}|{header_text}|{body_text}\\n"
    ser.write(frame.encode())
    prefix = "USB API RESPONSE-->"
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if not line.startswith(prefix):
            continue
        payload = json.loads(line[len(prefix) :])
        body_raw = payload.get("body")
        if isinstance(body_raw, str):
            try:
                payload["body"] = json.loads(body_raw)
            except json.JSONDecodeError:
                pass
        return payload


if __name__ == "__main__":
    port = "/dev/ttyACM0"  # adjust for your platform
    print(send_and_receive(port, "/api/version"))
    # Authenticated call: fetch challenge then include headers
    challenge_resp = send_and_receive(port, "/api/auth/challenge")
    print("challenge", challenge_resp.get("body"))
</code></pre>
    <p>The helper opens the serial connection, writes a framed request, and parses the JSON response emitted by the firmware. Expand it with additional routes as needed.</p>
  </div>
  <p><a href="index.html">Back to API reference</a></p>
</body>
</html>
"""


def write_docs(routes: List[RouteDoc]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    html_content = build_html(routes)
    (DOCS_DIR / "routes.html").write_text(html_content, encoding="utf-8")
    (DOCS_DIR / "authentication.html").write_text(
        build_authentication_html(), encoding="utf-8"
    )
    (DOCS_DIR / "network.html").write_text(build_network_html(), encoding="utf-8")
    (DOCS_DIR / "discovery.html").write_text(build_discovery_html(), encoding="utf-8")
    (DOCS_DIR / "usb.html").write_text(build_usb_html(), encoding="utf-8")


def main() -> None:
    routes = extract_routes()
    write_docs(routes)
    print(f"Generated docs for {len(routes)} routes at {DOCS_DIR}")


if __name__ == "__main__":
    main()
