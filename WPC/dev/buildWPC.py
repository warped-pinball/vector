#! /usr/bin/env python3

import argparse
import gzip
import json
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
SOURCE_DIR_DEFAULT = "..\src"
WPC_SOURCE_DIR_DEFAULT = "src"
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
    def __init__(self, build_dir, source_dir, environment="dev"):
        self.build_dir = build_dir
        self.source_dir = source_dir
        self.wpc_source_dir = WPC_SOURCE_DIR_DEFAULT
        self.environment = environment

    @step_report
    def copy_files_to_build(self):
        """Copy all files from root vector source_dir to build_dir - ignore config directory."""
        print("Copying files to build directory...")
        if os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)
        
        def ignore_config(src, names):
            return [name for name in names if name == "config"]
        
        shutil.copytree(self.source_dir, self.build_dir, ignore=ignore_config)

        # now copy WPC source files (may overwrite some root vector files)
        print(f"Copying WPC source files from {self.wpc_source_dir}...")
            
        for root, dirs, files in os.walk(self.wpc_source_dir):
            # Calculate the relative path from wpc_source_dir
            rel_path = os.path.relpath(root, self.wpc_source_dir)
            
            # Create the corresponding target directory if it doesn't exist
            target_dir = os.path.join(self.build_dir, rel_path)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
                
            # Copy each file, overwriting if it exists
            for file in files:
                source_file = os.path.join(root, file)
                target_file = os.path.join(target_dir, file)
                
                # Copy the file (this will overwrite if the file exists)
                shutil.copy2(source_file, target_file)



    @step_report
    def compile_py_files(self):
        """Compile .py files to .mpy bytecode, handling boot.py and main.py specially."""
        print("Compiling .py files to .mpy...")
        boot_py = os.path.join(self.build_dir, "boot.py")
        main_py = os.path.join(self.build_dir, "main.py")
        #if os.path.exists(boot_py):
        #    os.rename(boot_py, os.path.join(self.build_dir, "mboot.py"))
        #if os.path.exists(main_py):
        #    os.rename(main_py, os.path.join(self.build_dir, "mmain.py"))

        for root, dirs, files in os.walk(self.build_dir):
            for file in files:
                if file.endswith(".py") and file != "main.py" and file != "boot.py":
                    py_file = os.path.join(root, file)
                    cmd = f"{MPY_CROSS} -O3 {py_file}"
                    result = subprocess.run(cmd, shell=True)
                    if result.returncode != 0:
                        print(f"Error compiling {py_file}")
                        sys.exit(1)
                    os.remove(py_file)

        # Recreate boot.py and main.py to import .mpy
        #mboot_mpy = os.path.join(self.build_dir, "mboot.mpy")
        #if os.path.exists(mboot_mpy):
        #    with open(os.path.join(self.build_dir, "boot.py"), "w") as f:
        #        f.write("import mboot\n")

        '''
        mmain_mpy = os.path.join(self.build_dir, "mmain.mpy")
        if os.path.exists(mmain_mpy):
            with open(os.path.join(self.build_dir, "main.py"), "w") as f:
                f.write("import mmain\n")
        '''


    @step_report
    def minify_web_files(self):
        """Minify HTML, CSS, and JS files in build/web."""
        print("Minifying web files...")
        web_dir = os.path.join(self.build_dir, "web")
        if not os.path.isdir(web_dir):
            print("No 'web' directory found in build_dir; skipping.")
            return

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

    @step_report
    def combine_json_configs(self):
        """Combine JSON files in build/config into all.jsonl."""
        print("Combining JSON config files...")
        config_dir = os.path.join(self.build_dir, "config")
        if not os.path.isdir(config_dir):
            print("No 'config' directory found; skipping.")
            return
        output_path = os.path.join(config_dir, "all.jsonl")
        with open(output_path, "w") as outfile:
            for root, dirs, files in os.walk(config_dir):
                for file in files:
                    if file.endswith(".json") and file != "all.jsonl":
                        file_path = os.path.join(root, file)
                        with open(file_path, "r") as f:
                            data = json.load(f)
                        file_name = os.path.splitext(file)[0]
                        outfile.write(f"{file_name}{json.dumps(data, separators=(',',':'))}\n")
                        os.remove(file_path)

    @step_report
    def zip_files(self):
        """gzip all files in build/web subdirectories (but not build/web itself)."""
        print("Zipping files in subdirectories...")
        web_dir = os.path.join(self.build_dir, "web")
        if not os.path.isdir(web_dir):
            print("No 'web' directory found; skipping zip step.")
            return

        # zip each subdirectory (e.g. web/css, web/js, web/svg, etc.)
        for item in os.listdir(web_dir):
            item_path = os.path.join(web_dir, item)
            if os.path.isdir(item_path):
                self.gzip_directory(item_path)

    def gzip_directory(self, directory):
        print(f"Gzipping files in {directory}...")
        for root, dirs, files in os.walk(directory):
            for file in files:
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
    parser.add_argument("--env", default="dev", help="Build environment (dev, test, prod, etc.)")
    args = parser.parse_args()

    builder = Builder(args.build_dir, args.source_dir, args.env)

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
