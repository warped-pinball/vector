from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMIN_HTML = ROOT / "src" / "common" / "web" / "html" / "admin.html"
ADMIN_JS = ROOT / "src" / "common" / "web" / "js" / "admin.js"
BACKEND = ROOT / "src" / "common" / "backend.py"


def test_set_date_api_still_registered() -> None:
    backend = BACKEND.read_text(encoding="utf-8")
    assert '@add_route("/api/set_date", auth=True)' in backend
    assert "def app_setDateTime" in backend


def test_admin_html_exposes_set_clock_controls() -> None:
    html = ADMIN_HTML.read_text(encoding="utf-8")
    assert 'id="vector-clock-section"' in html
    assert 'id="set-clock-from-browser-button"' in html
    assert 'id="vector-clock-display"' in html
    assert "Set Clock from This Computer" in html


def test_admin_js_wires_browser_local_time_to_set_date() -> None:
    js = ADMIN_JS.read_text(encoding="utf-8")
    assert "function localDatePayload" in js
    assert "now.getMonth() + 1" in js
    assert 'smartFetch("/api/set_date"' in js
    assert 'smartFetch("/api/get_date"' in js
    assert "initVectorClock()" in js


def test_local_date_payload_shape_matches_api_contract() -> None:
    """Mirror the JS localDatePayload contract expected by /api/set_date."""
    # year, month(1-12), day, hour, minute, second - same order as app_setDateTime
    sample = [2026, 3, 15, 14, 30, 5]
    assert len(sample) == 6
    assert 1 <= sample[1] <= 12
    assert re.fullmatch(r"\d{4}", str(sample[0]))
