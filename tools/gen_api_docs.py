"""Generate static HTTP API documentation for backend routes.

This script statically parses ``src/common/backend.py`` using ``ast`` and writes
Markdown documentation to the ``docs`` directory for MkDocs. It avoids importing
any MicroPython-specific modules so it can run in standard CPython.
"""
from __future__ import annotations

import ast
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


# --- Markdown rendering ---------------------------------------------------


def _md_inline(text: str) -> str:
    return " ".join(text.strip().split())


def render_request_fields(route: RouteDoc) -> str:
    doc_req = (route.doc_block or {}).get("request", {}) if route.doc_block else {}
    sections = [
        ("query", "Query parameters"),
        ("body", "Body parameters"),
        ("headers", "Header parameters"),
    ]
    md_parts: List[str] = []
    for section, title in sections:
        entries: List[str] = []
        if doc_req and section in doc_req:
            for item in doc_req.get(section, []):
                if isinstance(item, dict):
                    name = _md_inline(str(item.get("name", "")))
                    desc = _md_inline(str(item.get("description", "")))
                    typ = _md_inline(str(item.get("type", "")))
                    req = "required" if item.get("required") else "optional"
                    pieces = [f"`{name}`"]
                    if typ:
                        pieces.append(typ)
                    pieces.append(req)
                    suffix = " - " + desc if desc else ""
                    entries.append(f"- {' '.join(pieces)}{suffix}")
        else:
            inferred = sorted(route.inferred_fields.get(section, []))
            for key in inferred:
                entries.append(f"- `{_md_inline(key)}` (inferred)")
        if entries:
            md_parts.extend([f"#### {title}", "", *entries, ""])
    return "\n".join(md_parts).strip()


def render_response(route: RouteDoc) -> str:
    if route.doc_block and "response" in route.doc_block:
        resp = route.doc_block["response"]
        parts = []
        if isinstance(resp, dict):
            if "status_codes" in resp:
                sc_list = resp.get("status_codes", [])
                status_entries = []
                for item in sc_list:
                    if isinstance(item, dict):
                        code = _md_inline(str(item.get("code", "")))
                        desc = _md_inline(str(item.get("description", "")))
                        suffix = f" - {desc}" if desc else ""
                        status_entries.append(f"- `{code}`{suffix}")
                if status_entries:
                    parts.extend(["#### Status codes", "", *status_entries, ""])
            if "body" in resp:
                body = resp["body"]
                if isinstance(body, dict):
                    body_desc = _md_inline(str(body.get("description", "")))
                    example = body.get("example")
                    if body_desc:
                        parts.append(f"**Response body:** {body_desc}")
                    if example is not None:
                        parts.extend(
                            ["", "```", str(example).strip(), "```", ""]
                        )
        if parts:
            return "\n".join(parts).strip()
    return "No structured response documented."


def render_route(route: RouteDoc) -> str:
    doc = route.doc_block or {}
    summary = _md_inline(str(doc.get("summary", ""))) if doc else ""
    description = summary or "No description provided."
    handler_link = f"{REPO_URL}/blob/main/src/common/backend.py#L{route.lineno}"
    auth_note = (
        "Authentication: Required (see [Authentication guide](authentication.md))."
        if route.auth
        else None
    )
    cooldown_note = (
        f"Cooldown: {route.cool_down_seconds}s" if route.cool_down_seconds else None
    )
    single_note = "Single instance: Yes" if route.single_instance else None

    request_fields = render_request_fields(route)
    response_block = render_response(route)

    description_lines = []
    if doc:
        if "summary" in doc:
            description_lines.append(_md_inline(str(doc.get("summary"))))
        extra_desc = doc.get("description")
        if extra_desc:
            description_lines.append(_md_inline(str(extra_desc)))
    else:
        description_lines.append(description)

    anchor = route.path.strip("/").replace("/", "-") or "root"

    notes = [note for note in (auth_note, cooldown_note, single_note) if note]
    note_block = "\n".join(f"- {note}" for note in notes)

    return "\n".join(
        [
            f"<a id=\"{anchor}\"></a>",
            f"## `{route.path}`",
            "",
            f"- **Handler:** [`{route.handler}`]({handler_link})",
            note_block if note_block else "",
            "",
            *description_lines,
            "",
            "### Request",
            "",
            request_fields or "No parameters inferred.",
            "",
            "### Response",
            "",
            response_block,
            "",
        ]
    ).strip()


def render_index(routes: List[RouteDoc]) -> str:
    items = []
    for route in routes:
        anchor = route.path.strip("/").replace("/", "-") or "root"
        items.append(f"- [`{route.path}`](#{anchor})")
    return "\n".join(items)


def build_markdown(routes: List[RouteDoc]) -> str:
    sections = "\n\n".join(render_route(r) for r in routes)
    index = render_index(routes)
    return "\n".join(
        [
            "# Vector HTTP API",
            "",
            "Generated automatically from `src/common/backend.py`. Use this page as the landing pad for connectivity guides and endpoint documentation.",
            "",
            "## Quick links",
            "",
            f"- [Main repository]({REPO_URL})",
            f"- [Latest release]({REPO_URL}/releases/latest)",
            f"- [WarpedPinball.com]({WARP_URL})",
            f"- [Live demo]({DEMO_URL})",
            "",
            "## Connectivity guides",
            "",
            "- [Authentication](authentication.md)",
            "- [Network access](network.md)",
            "- [Peer discovery](discovery.md)",
            "- [USB transport](usb.md)",
            "",
            "## Routes & endpoints",
            "",
            "Jump directly to a handler. Links open source on GitHub with accurate line numbers.",
            "",
            index,
            "",
            "---",
            "",
            sections,
            "",
        ]
    )


def write_docs(routes: List[RouteDoc]) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    markdown_content = build_markdown(routes)
    # Only the route index is generated automatically; the supplemental
    # guides are maintained as static files under docs/.
    (DOCS_DIR / "routes.md").write_text(markdown_content, encoding="utf-8")


def main() -> None:
    routes = extract_routes()
    write_docs(routes)
    print(f"Generated docs for {len(routes)} routes at {DOCS_DIR}")


if __name__ == "__main__":
    main()
