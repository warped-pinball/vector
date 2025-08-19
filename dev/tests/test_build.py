import sys

import dev.build as build


def test_default_build_dir(monkeypatch):
    recorded = {}

    class DummyBuilder:
        def __init__(self, build_dir, source_dir, target_hardware):
            recorded["build_dir"] = build_dir
            recorded["source_dir"] = source_dir
            recorded["target_hardware"] = target_hardware

        def copy_files_to_build(self):
            pass

        def compile_py_files(self):
            pass

        def minify_web_files(self):
            pass

        def scour_svg_files(self):
            pass

        def combine_json_configs(self):
            pass

        def zip_files(self):
            pass

    monkeypatch.setattr(build, "Builder", DummyBuilder)

    monkeypatch.setattr(sys, "argv", ["build.py", "--target_hardware", "wpc"])
    build.main()

    assert recorded["build_dir"] == "build/wpc"
