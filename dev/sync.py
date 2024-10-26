#!/usr/bin/env python3

import os
import sys
import subprocess
import shutil
from pathlib import Path

# Configuration
PICO_PORT = '/dev/ttyACM0'  # Update this to your Pico's port
SOURCE_DIR = 'src'          # Source directory containing your code
BUILD_DIR = 'build'         # Build directory for compiled and minified files
MPY_CROSS = 'mpy-cross'     # Path to the mpy-cross compiler
JS_MINIFY_DIRS = ['src/js']     # Directories containing JavaScript files to minify
CSS_MINIFY_DIRS = ['src/css']   # Directories containing CSS files to minify

def check_mpy_cross():
    """Check if mpy-cross is available."""
    result = subprocess.run(f"{MPY_CROSS} --version", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("mpy-cross not found. Please ensure mpy-cross is installed and in your PATH.")
        sys.exit(1)

def wipe_pico():
    """Wipe all files from the Pico."""
    print("Wiping Pico's filesystem...")
    cmd = f"""mpremote connect {PICO_PORT} exec "
import os
def remove(path):
    try:
        os.remove(path)
    except OSError:
        # It's a directory
        for entry in os.listdir(path):
            remove('/'.join((path, entry)))
        os.rmdir(path)
for entry in os.listdir('/'):
    remove('/' + entry)
" """
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("Error wiping Pico's filesystem.")
        sys.exit(1)

def compile_py_files():
    """Compile .py files to .mpy bytecode."""
    print("Compiling .py files to .mpy...")
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    shutil.copytree(SOURCE_DIR, BUILD_DIR)

    # Find and compile all .py files in BUILD_DIR
    for root, dirs, files in os.walk(BUILD_DIR):
        for file in files:
            if file.endswith('.py'):
                py_file = os.path.join(root, file)
                # Compile to .mpy
                cmd = f"{MPY_CROSS} {py_file}"
                result = subprocess.run(cmd, shell=True)
                if result.returncode != 0:
                    print(f"Error compiling {py_file}")
                    sys.exit(1)
                # Remove the .py file after compilation
                os.remove(py_file)

def minify_js_files():
    """Minify JavaScript files."""
    print("Minifying JavaScript files...")
    try:
        from jsmin import jsmin
    except ImportError:
        print("jsmin module not found. Please install it with 'pip install jsmin'")
        sys.exit(1)
    for js_dir in JS_MINIFY_DIRS:
        full_js_dir = js_dir.replace(SOURCE_DIR, BUILD_DIR)
        if os.path.exists(full_js_dir):
            for root, dirs, files in os.walk(full_js_dir):
                for file in files:
                    if file.endswith('.js'):
                        js_file = os.path.join(root, file)
                        with open(js_file, 'r') as f:
                            minified = jsmin(f.read())
                        with open(js_file, 'w') as f:
                            f.write(minified)

def minify_css_files():
    """Minify CSS files."""
    print("Minifying CSS files...")
    try:
        from csscompressor import compress
    except ImportError:
        print("csscompressor module not found. Please install it with 'pip install csscompressor'")
        sys.exit(1)
    for css_dir in CSS_MINIFY_DIRS:
        full_css_dir = css_dir.replace(SOURCE_DIR, BUILD_DIR)
        if os.path.exists(full_css_dir):
            for root, dirs, files in os.walk(full_css_dir):
                for file in files:
                    if file.endswith('.css'):
                        css_file = os.path.join(root, file)
                        with open(css_file, 'r') as f:
                            minified = compress(f.read())
                        with open(css_file, 'w') as f:
                            f.write(minified)

def copy_files_to_pico():
    """Copy all files from BUILD_DIR to the Pico's root directory."""
    print("Copying files to Pico...")
    # Change to the BUILD_DIR to ensure relative paths are correct
    original_dir = os.getcwd()
    os.chdir(BUILD_DIR)
    try:
        cmd = f"mpremote connect {PICO_PORT} fs cp -r . :"
        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            print("Error copying files to Pico.")
            sys.exit(1)
    finally:
        # Change back to the original directory
        os.chdir(original_dir)
    print("Sync complete.")

def main():
    try:
        check_mpy_cross()
        wipe_pico()
        compile_py_files()
        minify_js_files()
        minify_css_files()
        copy_files_to_pico()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
