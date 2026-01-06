from pathlib import Path

import tools.gen_api_docs as gen_api_docs


def test_write_docs_only_generates_routes(tmp_path, monkeypatch) -> None:
    docs_dir = tmp_path / "docs"
    monkeypatch.setattr(gen_api_docs, "DOCS_DIR", docs_dir)

    gen_api_docs.write_docs([])

    assert docs_dir.exists()
    written_files = {p.name for p in docs_dir.iterdir()}
    assert written_files == {"routes.html"}
    assert (docs_dir / "routes.html").read_text()
