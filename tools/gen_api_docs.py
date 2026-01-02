"""Generate static HTTP API documentation for backend routes.

This script statically parses ``src/common/backend.py`` using ``ast`` and writes
HTML documentation to the ``docs`` directory. It avoids importing any
MicroPython-specific modules so it can run in standard CPython.
"""
from __future__ import annotations

import ast
import html
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = REPO_ROOT / "src" / "common" / "backend.py"
DOCS_DIR = REPO_ROOT / "docs"


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

    for raw_line in block_lines:
        if not raw_line.strip() or raw_line.strip().startswith("#"):
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
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        parent_container = container
        if isinstance(parent_container, list):
            if not parent_container or not isinstance(parent_container[-1], dict):
                parent_container.append({})
            parent_container = parent_container[-1]

        if value:
            parent_container[key] = parse_scalar(value)
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
    handler_link = f"<a href='../src/common/backend.py#L{route.lineno}'>{html.escape(route.handler)}</a>"
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
    return f"<ul>{items}</ul>"


def build_html(routes: List[RouteDoc]) -> str:
    sections = "".join(render_route(r) for r in routes)
    index = render_index(routes)
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
      margin: 2.5rem auto;
      padding: 0 1.5rem 3rem;
      max-width: 1024px;
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
    section {{ border-bottom: 1px solid var(--panel-border); padding-bottom: 1.25rem; margin-bottom: 1.5rem; }}
    .meta {{ color: var(--muted); font-size: 0.95rem; margin: 0.35rem 0; }}
    .tag {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.85rem; border: 1px solid var(--panel-border); background: rgba(56,189,248,0.1); color: var(--accent); }}
  </style>
</head>
<body>
  <h1>Vector HTTP API</h1>
  <div class="panel">
    <p class="meta">Generated automatically from <code>src/common/backend.py</code>. Refer to request parameter locations for specifics.</p>
    <p class="meta">Authentication flow is documented separately in <a href="authentication.html">Authentication</a>.</p>
    <h2>Endpoints</h2>
    <div class="endpoint-list">{index}</div>
  </div>
  <div class="panel">{sections}</div>
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
  <p><a href="index.html">Back to API reference</a></p>
</body>
</html>
"""


def write_docs(routes: List[RouteDoc]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    html_content = build_html(routes)
    (DOCS_DIR / "index.html").write_text(html_content, encoding="utf-8")
    (DOCS_DIR / "authentication.html").write_text(
        build_authentication_html(), encoding="utf-8"
    )


def main() -> None:
    routes = extract_routes()
    write_docs(routes)
    print(f"Generated docs for {len(routes)} routes at {DOCS_DIR}")


if __name__ == "__main__":
    main()
