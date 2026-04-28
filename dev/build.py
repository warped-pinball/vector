#! /usr/bin/env python3

import argparse
import gzip
import json
import re
import zlib
import math
import os
import shutil
import subprocess
import sys
import time

from bs4 import BeautifulSoup
from csscompressor import compress
from htmlmin import minify as minify_html
from jsmin import jsmin

BUILD_DIR_DEFAULT = "build"
SOURCE_DIR_DEFAULT = "src"
MPY_CROSS = "mpy-cross"


def get_directory_size(path: str) -> tuple[int, int]:
    total_size = 0
    file_system_block_size = 4096
    space_lost_to_blocks = 0
    for dirpath, _, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                number_of_blocks = math.ceil(file_size / file_system_block_size)
                true_size = number_of_blocks * file_system_block_size
                space_lost_to_blocks += true_size - file_size
                total_size += true_size
    return total_size, space_lost_to_blocks


def step_report(func):
    """Decorator that prints timing and size info for each step."""

    def wrapper(*args, **kwargs):
        print(f"\nRunning step: {func.__name__}")
        original_size, _ = get_directory_size(args[0].build_dir)
        start_time = time.time()

        func(*args, **kwargs)

        elapsed_time = time.time() - start_time
        print(f"Step completed in {elapsed_time:.2f} seconds.")
        total_size, file_system_loss = get_directory_size(args[0].build_dir)
        print(f"Total size of files in build directory: {total_size / 1024:.2f} KB")
        print(f"Space lost to file system blocks: {file_system_loss / 1024:.2f} KB")
        diff = total_size - original_size
        if original_size:
            perc = (diff / original_size) * 100
            print(f"Size difference: {diff / 1024:.2f} KB ({perc:.2f}%)")
        print("-" * 40)

    return wrapper


class Builder:
    def __init__(self, build_dir, source_dir, target_hardware="sys11"):
        self.build_dir = build_dir
        self.source_dir = source_dir
        self.target_hardware = target_hardware

    @step_report
    def copy_files_to_build(self):
        """Copy all files from source_dir to build_dir."""
        print("Copying files to build directory...")
        if os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)

        common_src = os.path.join(self.source_dir, "common")
        shutil.copytree(common_src, self.build_dir)

        sys_src_path = os.path.join(self.source_dir, self.target_hardware)
        for root, dirs, files in os.walk(sys_src_path):
            rel_path = os.path.relpath(root, sys_src_path)
            dest_dir = os.path.join(self.build_dir, rel_path)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
            for file in files:
                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, file)
                shutil.copy2(src_file, dest_file)

    @step_report
    def compile_py_files(self):
        """Compile .py files to .mpy bytecode, handling boot.py and main.py specially."""
        print("Compiling .py files to .mpy...")
        boot_py = os.path.join(self.build_dir, "boot.py")
        main_py = os.path.join(self.build_dir, "main.py")
        if os.path.exists(boot_py):
            os.rename(boot_py, os.path.join(self.build_dir, "mboot.py"))
        if os.path.exists(main_py):
            os.rename(main_py, os.path.join(self.build_dir, "mmain.py"))

        for root, dirs, files in os.walk(self.build_dir):
            for file in files:
                # skip Python files whose base name ends with "viper"
                if file.endswith(".py"):
                    name_noext = os.path.splitext(file)[0]
                    if name_noext.lower().endswith("viper"):
                        # leave the .py file in place and skip compiling
                        print(f"Skipping viper file: {os.path.join(root, file)}")
                        continue
                    py_file = os.path.join(root, file)
                    cmd = f"{MPY_CROSS} -O3 {py_file}"
                    result = subprocess.run(cmd, shell=True)
                    if result.returncode != 0:
                        print(f"Error compiling {py_file}")
                        sys.exit(1)
                    os.remove(py_file)

        # Recreate boot.py and main.py to import .mpy
        mboot_mpy = os.path.join(self.build_dir, "mboot.mpy")
        if os.path.exists(mboot_mpy):
            with open(os.path.join(self.build_dir, "boot.py"), "w") as f:
                f.write("import mboot\n")

        mmain_mpy = os.path.join(self.build_dir, "mmain.mpy")
        if os.path.exists(mmain_mpy):
            with open(os.path.join(self.build_dir, "main.py"), "w") as f:
                f.write("import mmain\n")

    def _get_vector_version(self):
        """Read VectorVersion from SharedState.py for the target hardware.

        Looks in the target-specific source first (e.g. src/em/SharedState.py
        overrides src/common/SharedState.py for the 'em' target), then falls
        back to the common source file.  The source files are used rather than
        the build-dir copies because compile_py_files() deletes the .py files
        before minify_web_files() runs.
        """
        candidates = [
            os.path.join(self.source_dir, self.target_hardware, "SharedState.py"),
            os.path.join(self.source_dir, "common", "SharedState.py"),
        ]
        for path in candidates:
            if os.path.exists(path):
                with open(path, "r") as f:
                    for line in f:
                        m = re.match(r'VectorVersion\s*=\s*["\']([^"\']+)["\']', line)
                        if m:
                            return m.group(1)
        return None

    @step_report
    def minify_web_files(self):
        """Minify HTML, CSS, and JS files in build/web."""
        print("Minifying web files...")
        web_dir = os.path.join(self.build_dir, "web")
        if not os.path.isdir(web_dir):
            print("No 'web' directory found in build_dir; skipping.")
            return

        # Read firmware version once so we can embed it in static asset URLs.
        # This turns /js/utils.js into /js/utils.js?v=1.2.3 which the browser
        # treats as a new resource whenever the version changes, automatically
        # busting any immutable cached copies without JS-based invalidation.
        version = self._get_vector_version()
        if version:
            print(f"Injecting ?v={version} into HTML static asset URLs...")
        else:
            print("Warning: could not determine VectorVersion; skipping URL versioning.")

        for root, dirs, files in os.walk(web_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if file.endswith(".html"):
                    content = self.read_file(file_path)
                    soup = BeautifulSoup(content, "html.parser")
                    # Minify inline JS
                    for script_tag in soup.find_all("script"):
                        if script_tag.string:
                            script_tag.string.replace_with(jsmin(script_tag.string))
                    # Minify inline CSS
                    for style_tag in soup.find_all("style"):
                        if style_tag.string:
                            style_tag.string.replace_with(compress(style_tag.string))
                    # Inject version query param into local static asset URLs so
                    # Cache-Control: immutable entries are automatically replaced
                    # when the firmware version changes.  Only same-origin paths
                    # (starting with /) are touched; external URLs and .html
                    # navigation links are left unchanged.
                    if version:
                        for tag in soup.find_all("script", src=True):
                            src = tag.get("src", "")
                            if src.startswith("/") and "?" not in src:
                                tag["src"] = src + "?v=" + version
                        for tag in soup.find_all("link", href=True):
                            href = tag.get("href", "")
                            if href.startswith("/") and not href.endswith(".html") and "?" not in href:
                                tag["href"] = href + "?v=" + version
                    # Convert soup back to HTML and minify
                    final_html = minify_html(str(soup))
                    self.write_file(file_path, final_html)

                elif file.endswith(".css"):
                    content = self.read_file(file_path)
                    minified_css = compress(content)
                    self.write_file(file_path, minified_css)

                elif file.endswith(".js"):
                    content = self.read_file(file_path)
                    minified_js = jsmin(content)
                    self.write_file(file_path, minified_js)

        # Inject the firmware version and asset list into the service worker.
        # This must happen AFTER the walk loop so that all files have been
        # minified and the complete asset list is known.
        if version:
            sw_path = os.path.join(web_dir, "sw.js")
            if os.path.exists(sw_path):
                precache_urls = []
                for root2, _, files2 in os.walk(web_dir):
                    for f2 in sorted(files2):
                        if f2 == "sw.js":
                            continue
                        fp = os.path.join(root2, f2)
                        rel = os.path.relpath(fp, web_dir)
                        precache_urls.append("/" + rel.replace(os.sep, "/"))
                precache_urls.sort()
                cache_name = "vector-v" + version
                sw_content = self.read_file(sw_path)
                sw_content = sw_content.replace('"PLACEHOLDER_CACHE_NAME"', json.dumps(cache_name))
                sw_content = sw_content.replace('"PLACEHOLDER_PRECACHE_URLS"', json.dumps(precache_urls, separators=(",", ":")))
                if '"PLACEHOLDER_CACHE_NAME"' in sw_content or '"PLACEHOLDER_PRECACHE_URLS"' in sw_content:
                    raise RuntimeError("Failed to inject placeholders into sw.js — check that the source file contains the expected placeholder strings")
                self.write_file(sw_path, sw_content)
                print(f"Service worker: cache={cache_name!r}, {len(precache_urls)} assets pre-cached")

    @step_report
    def scour_svg_files(self):
        """Run scour on all svg files in build/web/svg directory."""
        print("Scouring SVG files...")
        svg_dir = os.path.join(self.build_dir, "web", "svg")
        if not os.path.isdir(svg_dir):
            print("No 'svg' directory found under build/web; skipping.")
            return

        for root, dirs, files in os.walk(svg_dir):
            for file in files:
                if file.endswith(".svg"):
                    file_path = os.path.join(root, file)
                    temp_file_path = file_path + ".tmp"
                    cmd = f"scour -i {file_path} " "--enable-viewboxing " "--enable-id-stripping " "--enable-comment-stripping " "--shorten-ids --indent=none " f"-o {temp_file_path}"
                    result = subprocess.run(cmd, shell=True)
                    if result.returncode == 0:
                        os.remove(file_path)
                        os.rename(temp_file_path, file_path)
                    else:
                        print(f"Error scouring {file_path}")

    def validate_linkto_references(self, config_dir):
        """Validate LinkTo references in JSON config files before combining."""
        configs = {}
        
        # Load all JSON files
        for root, dirs, files in os.walk(config_dir):
            for file in files:
                if file.endswith(".json"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r") as f:
                        data = json.load(f)
                    file_name = os.path.splitext(file)[0]
                    configs[file_name] = data
        
        # Validate LinkTo references
        link_count = 0
        errors = []
        
        for filename, data in configs.items():
            if isinstance(data.get("GameInfo"), dict) and "LinkTo" in data["GameInfo"]:
                link_count += 1
                target = data["GameInfo"]["LinkTo"]
                
                # Check target exists
                if target not in configs:
                    errors.append(f"ERROR: {filename} links to {target}, but {target}.json not found")
                    continue
                
                # Check target doesn't have LinkTo (no chaining)
                target_data = configs[target]
                if isinstance(target_data.get("GameInfo"), dict) and "LinkTo" in target_data["GameInfo"]:
                    errors.append(f"ERROR: {filename} links to {target}, but {target} also contains LinkTo (chaining not allowed)")
        
        # Report results
        if errors:
            print("LinkTo validation failed:")
            for error in errors:
                print(f"  {error}")
            raise ValueError(f"Found {len(errors)} LinkTo validation error(s)")
        
        if link_count > 0:
            print(f"Validated {link_count} LinkTo reference(s) - all valid")

    @step_report
    def combine_json_configs(self):
        """Combine JSON files in build/config into a deflate-compressed all.jsonl.z file."""
        print("Combining JSON config files...")
        config_dir = os.path.join(self.build_dir, "config")
        if not os.path.isdir(config_dir):
            print("No 'config' directory found; skipping.")
            return
        
        # Validate LinkTo references before combining
        self.validate_linkto_references(config_dir)
        
        output_path = os.path.join(config_dir, "all.jsonl.z")
        compressor = zlib.compressobj(level=9, wbits=8)
        with open(output_path, "wb") as outfile:
            for root, dirs, files in os.walk(config_dir):
                for file in files:
                    if file.endswith(".json"):
                        file_path = os.path.join(root, file)
                        with open(file_path, "r") as f:
                            data = json.load(f)
                        file_name = os.path.splitext(file)[0]
                        line = f"{file_name}{json.dumps(data, separators=(',',':'))}\n"
                        outfile.write(compressor.compress(line.encode("utf-8")))
                        os.remove(file_path)
            outfile.write(compressor.flush())

    @step_report
    def zip_files(self):
        """gzip applicable files in build/web."""
        print("Zipping web files...")
        web_dir = os.path.join(self.build_dir, "web")
        if not os.path.isdir(web_dir):
            print("No 'web' directory found; skipping zip step.")
            return

        self.gzip_directory(web_dir)

    def gzip_directory(self, directory):
        print(f"Gzipping files in {directory}...")
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(".gz"):
                    # Skip existing gzip files
                    continue
                file_path = os.path.join(root, file)
                with open(file_path, "rb") as f:
                    content = f.read()

                gz_path = file_path + ".gz"

                # Replicate the "-n" effect from the CLI by setting a fixed timestamp
                # This is required to ensure the gzip files are
                # byte-for-byte identical to get matching checksums
                zipper = gzip.GzipFile(gz_path, "wb", compresslevel=9, mtime=0)
                zipper.write(content)
                zipper.close()

                os.remove(file_path)

    def read_file(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, filepath, content):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)


def main():
    parser = argparse.ArgumentParser(description="Build the project into a specified build directory.")
    parser.add_argument("--build-dir", default=BUILD_DIR_DEFAULT, help="Path to the build directory")
    parser.add_argument("--source-dir", default=SOURCE_DIR_DEFAULT, help="Path to the source directory")
    parser.add_argument(
        "--target_hardware",
        default="sys11",
        help="Target system for the build (e.g., data_east, sys11, whitestar, wpc, em, etc.)",
    )
    args = parser.parse_args()

    if args.build_dir == BUILD_DIR_DEFAULT:
        args.build_dir = os.path.join(args.build_dir, args.target_hardware)

    builder = Builder(args.build_dir, args.source_dir, args.target_hardware)

    # Run build steps in sequence
    builder.copy_files_to_build()
    builder.compile_py_files()
    builder.minify_web_files()
    builder.scour_svg_files()
    builder.combine_json_configs()
    builder.zip_files()

    # Potentially create a final zip or artifact of the entire build_dir here
    # e.g., shutil.make_archive("my_build_artifact", "zip", args.build_dir)

    print("Build complete.")


if __name__ == "__main__":
    main()
