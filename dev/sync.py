#! /usr/bin/env python3

import os
import sys
import subprocess
import shutil
from pathlib import Path
import argparse
import serial.tools.list_ports
import json
import time
import gzip
import math

# Configuration
PICO_PORT = None  # Placeholder for auto-detected port
REPL_RETRY_DELAY = 1  # Delay between retries in seconds
REPL_MAX_RETRIES = 5  # Maximum number of retries to connect to REPL
SOURCE_DIR = 'src'  # Source directory containing your code
BUILD_DIR = 'build'  # Build directory for compiled and minified files
MPY_CROSS = 'mpy-cross'  # Path to the mpy-cross compiler
JS_MINIFY_DIRS = ['src/web/js']  # Directories containing JavaScript files to minify
CSS_MINIFY_DIRS = ['src/web/css']  # Directories containing CSS files to minify
HTML_MINIFY_DIRS = ['src/web']  # Directories containing HTML files to minify
GIT_COMMIT_FILE = 'git_commit.txt'  # File to store git commit hash

#TODO calculate number of 4Kb blocks we need to fit all files in the Pico (since that's the block size)

def get_directory_size(path: str) -> tuple[int, int]:
    total_size = 0
    file_system_block_size = 4096
    space_lost_to_blocks = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            # Only add the file size if it exists (avoid broken symlinks, etc.)
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                
                number_of_blocks = math.ceil(file_size / file_system_block_size)
                true_size = number_of_blocks * file_system_block_size
                space_lost_to_blocks += true_size - file_size
                total_size += true_size
                
    return total_size, space_lost_to_blocks

def step_report(size_report=False, time_report=True):
    def build_step_report(func):
        """Decorator to print a step report."""
        def wrapper(*args, **kwargs):
            print()
            print(f"Running step: {func.__name__}")
            if size_report:
                original_size, _ = get_directory_size(BUILD_DIR)
            start_time = time.time()
            func(*args, **kwargs)
            end_time = time.time()
            elapsed_time = end_time - start_time
            if time_report:
                print(f"Step completed in {elapsed_time:.2f} seconds.")
            if size_report:
                total_size, file_system_loss = get_directory_size(BUILD_DIR)
                print(f"Total size of files in build directory: {total_size / 1024:.2f} KB")
                print(f"Space lost to file system blocks: {file_system_loss / 1024:.2f} KB")
                if original_size:
                    size_diff = total_size - original_size
                    print(f"Size difference: {size_diff / 1024:.2f} KB ({size_diff / original_size * 100:.2f}%)")
            print('-' * 40)
        return wrapper
    return build_step_report

def autodetect_pico_port():
    """Auto-detect the Pico port using mpremote."""
    try:
        result = subprocess.run("mpremote connect list", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            output = result.stdout.decode().strip()
            if output:
                return output.split('\n')[0].split()[0]
        print("Unable to detect Pico port using mpremote. Please specify the correct port manually.")
    except Exception as e:
        print(f"Error detecting Pico port: {e}")
    sys.exit(1)

def check_mpy_cross():
    """Check if mpy-cross is available."""
    result = subprocess.run(f"{MPY_CROSS} --version", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("mpy-cross not found. Please ensure mpy-cross is installed and in your PATH.")
        sys.exit(1)

@step_report(time_report=True)
def wipe_pico():
    """Wipe all files from the Pico."""
    print("Wiping Pico's filesystem...")
    mpython = '\n'.join([
        "import os",
        "def remove(path):",
        "    try:",
        "        os.remove(path)",
        "    except OSError:",
        "        for entry in os.listdir(path):",
        "            remove('/'.join((path, entry)))",
        "        os.rmdir(path)",
        "for entry in os.listdir('/'):",
        "    remove('/' + entry)"
    ])
    cmd = f"mpremote connect {PICO_PORT} exec \"{mpython}\""
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("Error wiping Pico's filesystem.")
        print(result.stderr.decode())
        sys.exit(1)

@step_report(time_report=True, size_report=True)
def copy_files_to_build():
    """Copy all files from SOURCE_DIR to BUILD_DIR."""
    print("Copying files to build directory...")
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    shutil.copytree(SOURCE_DIR, BUILD_DIR)

@step_report(time_report=True, size_report=True)
def compile_py_files():
    """Compile .py files to .mpy bytecode, handling boot.py and main.py separately."""
    print("Compiling .py files to .mpy...")
    boot_py = os.path.join(BUILD_DIR, 'boot.py')
    main_py = os.path.join(BUILD_DIR, 'main.py')
    if os.path.exists(boot_py):
        os.rename(boot_py, os.path.join(BUILD_DIR, 'mboot.py'))
    if os.path.exists(main_py):
        os.rename(main_py, os.path.join(BUILD_DIR, 'mmain.py'))

    for root, dirs, files in os.walk(BUILD_DIR):
        for file in files:
            if file.endswith('.py'):
                py_file = os.path.join(root, file)
                cmd = f"{MPY_CROSS} {py_file}"
                result = subprocess.run(cmd, shell=True)
                if result.returncode != 0:
                    print(f"Error compiling {py_file}")
                    sys.exit(1)
                os.remove(py_file)

    create_minimal_boot_main()

@step_report(time_report=True, size_report=True)
def create_minimal_boot_main():
    """Create minimal boot.py and main.py that import mboot.mpy and mmain.mpy."""
    print("Creating minimal boot.py and main.py...")
    mboot_mpy = os.path.join(BUILD_DIR, 'mboot.mpy')
    if os.path.exists(mboot_mpy):
        boot_py_content = "import mboot\n"
        with open(os.path.join(BUILD_DIR, 'boot.py'), 'w') as f:
            f.write(boot_py_content)
    mmain_mpy = os.path.join(BUILD_DIR, 'mmain.mpy')
    if os.path.exists(mmain_mpy):
        main_py_content = "import mmain\n"
        with open(os.path.join(BUILD_DIR, 'main.py'), 'w') as f:
            f.write(main_py_content)

@step_report(time_report=True, size_report=True)
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

@step_report(time_report=True, size_report=True)
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

@step_report(time_report=True, size_report=True)
def minify_html_files():
    """Minify HTML files."""
    print("Minifying HTML files...")
    try:
        from htmlmin import minify
    except ImportError:
        print("htmlmin module not found. Please install it with 'pip install htmlmin'")
        sys.exit(1)
    for html_dir in HTML_MINIFY_DIRS:
        full_html_dir = html_dir.replace(SOURCE_DIR, BUILD_DIR)
        if os.path.exists(full_html_dir):
            for root, dirs, files in os.walk(full_html_dir):
                for file in files:
                    if file.endswith('.html'):
                        html_file = os.path.join(root, file)
                        with open(html_file, 'r') as f:
                            minified = minify(f.read())
                        with open(html_file, 'w') as f:
                            f.write(minified)

@step_report(time_report=True, size_report=True)
def scour_svg_files():
    """run scour on all svg files in the build/web/svg directory."""
    print("Scouring SVG files...")
    for root, dirs, files in os.walk('build/web/svg'):
        for file in files:
            if file.endswith('.svg'):
                file_path = os.path.join(root, file)
                temp_file_path = file_path + '.tmp'
                cmd = f"scour -i {file_path} --enable-viewboxing --enable-id-stripping --enable-comment-stripping --shorten-ids --indent=none -o {temp_file_path}"
                result = subprocess.run(cmd, shell=True)
                if result.returncode == 0:
                    os.remove(file_path)
                    os.rename(temp_file_path, file_path)
                else:
                    print(f"Error scouring {file_path}")

@step_report(time_report=True, size_report=True)
def minify_json_files():
    """Minify JSON files."""
    print("Minifying JSON files...")
    paths = [
        os.path.join(BUILD_DIR, 'web'),
        os.path.join(BUILD_DIR, 'GameDefs')
    ]
    for path in paths:
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('.json'):
                    file_path = os.path.join(root, file)
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                    with open(file_path, 'w') as f:
                        json.dump(data, f, separators=(',', ':'))

@step_report(time_report=True, size_report=True)
def zip_files():
    """gzip all files in the build/web/* directory. (but not files in /web like web/index.html)"""
    print("Zipping files...")
    def zip_files_in_dir(dir):
        """gzip all files in the given directory."""
        print(f"Zipping files in {dir}...")
        for root, dirs, files in os.walk(dir):
            for file in files:
                file_path = os.path.join(root, file)
                with open(file_path, 'rb') as f:
                    content = f.read()
                with gzip.open(file_path + '.gz', 'wb', compresslevel=9) as f:
                    f.write(content)
                os.remove(file_path)

    # get list of directories in build/web
    web_dir = os.path.join(BUILD_DIR, 'web')
    web_dirs = [os.path.join(web_dir, d) for d in os.listdir(web_dir) if os.path.isdir(os.path.join(web_dir, d))]
    for dir in web_dirs:
        zip_files_in_dir(os.path.join(dir))
    
    zip_files_in_dir('build/GameDefs')
    
@step_report(time_report=True, size_report=True)
def copy_files_to_pico():
    """Copy all files from BUILD_DIR to the Pico's root directory."""
    print("Copying files to Pico...")
    original_dir = os.getcwd()
    os.chdir(BUILD_DIR)
    try:
        cmd = f"mpremote connect {PICO_PORT} fs cp -r . :"
        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            print("Error copying files to Pico.")
            sys.exit(1)
    finally:
        os.chdir(original_dir)
    print("Sync complete.")

@step_report(time_report=True)
def restart_pico():
    """Restart the Pico."""
    print("Restarting the Pico...")
    cmd = f"mpremote connect {PICO_PORT} exec --no-follow 'import machine; machine.reset()'"
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("Error restarting the Pico.")
        sys.exit(1)
    print("Pico restarted.")

@step_report(time_report=True)
def write_git_commit():
    """Write the current git commit hash to a file."""
    print("Writing git commit hash...")
    result = subprocess.run("git rev-parse HEAD", shell=True, stdout=subprocess.PIPE)
    if result.returncode == 0:
        commit_hash = result.stdout.decode().strip()
        with open(os.path.join(BUILD_DIR, GIT_COMMIT_FILE), 'w') as f:
            f.write(commit_hash + "\n")
    else:
        print("Error obtaining git commit hash.")
        sys.exit(1)

@step_report(time_report=True)
def read_git_commit_on_pico():
    """Read the git commit hash from the file on the Pico."""
    print("Reading git commit hash from Pico...")
    cmd = f"mpremote connect {PICO_PORT} fs cat {GIT_COMMIT_FILE}"
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        if "ENOENT" in result.stderr.decode():
            print(f"Git commit file '{GIT_COMMIT_FILE}' not found on Pico.")
        else:
            print("Error reading git commit hash from Pico.")
    else:
        print("Current git commit on Pico:")
        print(result.stdout.decode().strip())

@step_report(time_report=True)
def connect_to_repl():
    """Connect to the Pico REPL with retries."""
    retries = 0
    while retries < REPL_MAX_RETRIES:
        print(f"Attempting to connect to Pico REPL (try {retries + 1}/{REPL_MAX_RETRIES})...")
        cmd = f"mpremote connect {PICO_PORT} repl"
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            print("Connected to Pico REPL.")
            return
        else:
            retries += 1
            print(f"Attempt {retries} failed. Retrying in {REPL_RETRY_DELAY} seconds...")
            time.sleep(REPL_RETRY_DELAY)
    print(f"Failed to connect to Pico REPL after {REPL_MAX_RETRIES} attempts.")
    sys.exit(1)

@step_report(time_report=True)
def apply_local_config_to_pico():
    """
    Apply configuration from a JSON file to the Pico's configuration.

    filename: config.json
    example content:
    {
       "ssid": "Your WiFi SSID",
       "password": "Your WiFi Password",
       "gamename": "GenericSystem11",
       "Gpassword": ""
    }

    """

    # check for file in the same dir as this script
    config_file_path = Path(__file__).parent / 'config.json'
    if not config_file_path.exists():
        print("No local configuration file found to apply at: ", config_file_path)
        return
    
    print("Applying local configuration to Pico...")
    try:
        with open(config_file_path, 'r') as config_file:
            try:
                local_config = json.load(config_file)
            except json.JSONDecodeError as e:
                print(e)
                exit(1)
          
        # Construct a command to edit configuration in Pico using mpremote
        config_update_cmd = '\n'.join(
          [
            "import SPI_DataStore as datastore",
            "config = datastore.read_record('configuration')",
          ] +
          [
            f"config['{key}'] = '{value}'"
            for key, value in local_config.items()
          ] +
          [
            "datastore.write_record('configuration', config)"
          ]
        )

        cmd = f"mpremote connect {PICO_PORT} exec \"{config_update_cmd}\""
        
        for attempt in range(3):
            time.sleep(REPL_RETRY_DELAY)
            result = subprocess.run(cmd, shell=True)
            if result.returncode == 0:
                break
            print(f"Error applying configuration to Pico. Retrying... ({attempt + 1})")
        if result.returncode != 0:
            print("Error applying configuration to Pico.")
            sys.exit(1)
        print("Configuration updated successfully on Pico.")
    except Exception as e:
        print(f"Error reading or applying configuration: {e}")
        sys.exit(1)

def write_test_data():
    """Write test data to the Pico."""
    print("Writing test data to Pico...")
    test_data_file_path = Path(__file__).parent / 'test_data.json'
    if not test_data_file_path.exists():
        print("Test data file not found.")
        return
    with open(test_data_file_path, 'r') as f:
        test_data = json.load(f)

    # set player names

    test_data_update_cmd = '\n'.join(
        # set leaderboard data
        [
            # "import SPI_DataStore as datastore",
            "from ScoreTrack import update_leaderboard",
        ] +
        [
            f'update_leaderboard({json.dumps(record)})'
            for record in test_data["leaders"]
        ] +
        # turn on tournament mode
        [
            "import SharedState",
            "SharedState.tournamentModeOn = 1"
        ] +
        [
            f'update_leaderboard({json.dumps(record)})'
            for record in test_data["tournament"]
        ] +
        # turn off tournament mode
        [
            "SharedState.tournamentModeOn = 0"
        ]
    )

    cmd = f'mpremote connect {PICO_PORT} exec \'{test_data_update_cmd}\''
    for attempt in range(3):
        time.sleep(REPL_RETRY_DELAY)
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            break
        print(f"Error writing test data to Pico. Retrying... ({attempt + 1})")
    if result.returncode != 0:
        print("Error writing test data to Pico.")
        sys.exit(1)
    print("Test data written successfully to Pico.")

def main():
    parser = argparse.ArgumentParser(
    formatter_class=argparse.RawTextHelpFormatter,
    description="Pico Deployment Script",
    epilog='\n'.join([
        "Examples:",
        "  python script.py --steps all",
        "    Run all steps in order.",
        " ",
        "  python script.py --steps compile minify_js copy restart",
        "    Compile Python files, minify JavaScript, copy files to Pico, and restart.",
        " ",
        "  python script.py --skip wipe",
        "    Run all steps except wiping the Pico filesystem.",
        " ",
        "Steps are executed in the following order:",
        "  1. read_commit - Read the current git commit hash on the Pico.",
        "  2. wipe - Wipe the Pico filesystem.",
        "  3. build_init - Copy files to the build directory.",
        "  4. compile - Compile Python files to .mpy.",
        "  5. minify_js - Minify JavaScript files.",
        "  6. minify_css - Minify CSS files.",
        "  7. minify_html - Minify HTML files.",
        "  8. scour_svg - Run scour on all svg files in the build/web/svg directory.",
        "  9. minify_json - Minify JSON files.",
        " 10. zip - gzip all files in the build/web/* directory.",
        " 11. write_commit - Write the current git commit hash to a file.",
        " 12. copy - Copy files to the Pico.",
        " 13. restart - Restart the Pico.",
        " 14. apply_local_config - Apply local configuration from JSON file to the Pico.",
        " 15. write_test_data - Write test data to the Pico.",
        " 16. connect_repl - Connect to the Pico REPL."
    ])
)
    parser.add_argument(
        "--steps", nargs='+', 
        help="Specify steps to run in order (all, wipe, compile, minify_js, minify_css, copy, restart, write_commit, read_commit, apply_local_config).\n If 'all' is specified, all steps will be run in the defined order."
    )
    parser.add_argument(
        "--skip", nargs='+', 
        help="Specify steps to skip (wipe, compile, minify_js, minify_css, copy, restart, write_commit, read_commit, apply_local_config).\n This can be used to avoid specific operations during the deployment."
    )
    args = parser.parse_args()

    global PICO_PORT
    PICO_PORT = autodetect_pico_port()

    steps_to_run = [
        ("read_commit", read_git_commit_on_pico),
        ("wipe", wipe_pico),
        ("build_init", copy_files_to_build),
        ("compile", compile_py_files),
        ("minify_js", minify_js_files),
        ("minify_css", minify_css_files),
        ("minify_html", minify_html_files),
        ("scour_svg", scour_svg_files),
        ("minify_json", minify_json_files),
        ("zip", zip_files),
        ("write_commit", write_git_commit),
        ("copy", copy_files_to_pico),
        ("apply_local_config", apply_local_config_to_pico),
        ("write_test_data", write_test_data),
        ("restart", restart_pico),
        ("connect_repl", connect_to_repl),
    ]

    if args.steps and "all" not in args.steps:
        selected_steps = [step for step, func in steps_to_run if step in args.steps]
    else:
        selected_steps = [step for step, func in steps_to_run]

    if args.skip:
        selected_steps = [step for step in selected_steps if step not in args.skip]

    try:
        for step, func in steps_to_run:
            if step in selected_steps:
                func()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
