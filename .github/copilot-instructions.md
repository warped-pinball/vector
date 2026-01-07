# Copilot Instructions for Vector

## Project Overview

Vector is a modern hardware and software solution for classic pinball machines (Williams/Bally System 9/11, WPC, Data East). It provides WiFi connectivity, live scores, extended leaderboards, and modern features while preserving original gameplay.

## Technology Stack

- **Primary Language**: Python (MicroPython for embedded systems)
- **Hardware**: Raspberry Pi Pico
- **Frontend**: HTML, CSS, JavaScript (vanilla, no frameworks)
- **Backend**: MicroPython with custom web server (phew)
- **Build System**: Python-based build scripts
- **Version Control**: Git with pre-commit hooks

## Code Style and Conventions

### Python
- **Formatter**: Black with line length of 200 characters
- **Import Sorting**: isort with Black profile
- **Linter**: flake8 with max line length 200, ignoring E203, W503, E242, E231, E241
- **File Headers**: All Python files should include the CC BY-NC 4.0 license header:
  ```python
  # This file is part of the Warped Pinball SYS11Wifi Project.
  # https://creativecommons.org/licenses/by-nc/4.0/
  # This work is licensed under CC BY-NC 4.0
  ```

### JavaScript/HTML/CSS
- **Formatter**: Prettier (version 3.0.3)
- **Style**: Vanilla JavaScript, no frameworks or libraries (except minimal dependencies like js-sha256)
- **Files**: Exclude minified files (*.min.js, *.min.css) from formatting

### General Conventions
- Use descriptive variable names
- Follow existing patterns in the codebase
- Keep functions focused and single-purpose
- Add comments for complex logic, especially hardware interactions

## Development Workflow

### Setup
1. Use Python 3 with virtual environment (venv or conda)
2. Install dependencies: `pip install -r dev/requirements.txt`
3. Install pre-commit hooks: `pre-commit install`

### Building and Testing
- **Build Script**: `python dev/sync.py <target> [port]`
  - Targets: `sys11`, `wpc`, `em`, or `auto` for auto-detection
  - Example: `python dev/sync.py sys11 /dev/ttyACM0`
- **Auto Flash**: `python dev/sync.py auto` - detects and flashes all connected boards
- **Configuration**: Create `dev/config.json` for WiFi and game settings
- **Update Packages**: `python dev/build_update.py --version X.Y.Z --target_hardware sys11`

### Testing
- Tests are located in `dev/tests/`
- Run tests before submitting changes
- Test on actual hardware when possible (Pico + pinball machine recommended)
- Manual testing via web interface is important for UI changes

## Project Structure

- **`src/common/`**: Shared code across all hardware platforms
  - Core system files (main.py, boot.py, systemConfig.py)
  - Game logic (GameDefsLoad.py, GameStatus.py, ScoreTrack.py)
  - Storage (SPI_DataStore.py, FileIO.py)
  - Web server and frontend (web/, backend.py)
- **`src/sys11/`**, **`src/wpc/`**, **`src/em/`**, etc.: Platform-specific code
- **`dev/`**: Build scripts, tools, and tests
- **`docs/`**: Documentation
- **`.github/`**: GitHub configuration (issues, PRs, workflows)

## Important Constraints

### Performance
- **Memory-constrained**: Running on Raspberry Pi Pico with limited RAM
- **Optimize for size**: Use efficient data structures and algorithms
- **Minimize allocations**: Reuse objects when possible
- **Web assets**: Keep HTML/CSS/JS minimal; bundle/minify when appropriate

### Hardware Interaction
- Direct hardware control via machine.Pin and SPI
- Real-time requirements for pinball game state tracking
- Non-blocking operations preferred for web server

### Backwards Compatibility
- Maintain compatibility with existing Vector hardware
- Preserve saved game data and settings during updates
- Graceful fallbacks for older hardware revisions

## License Requirements

- This project is licensed under **CC BY-NC 4.0** (Creative Commons Attribution-NonCommercial)
- All code contributions must be compatible with this license
- Include license headers in new files
- Do not introduce dependencies with incompatible licenses

## Contributing Guidelines

1. **Open an issue first**: Discuss ideas before implementing (performance/technical constraints may exist)
2. Fork the repository and create a feature branch
3. Follow the code style and conventions
4. Test changes locally on hardware if possible
5. Submit a cross-fork pull request with:
   - Clear description of changes
   - Related issue links
   - Testing details
   - Screenshots for UI changes
6. Wait for review and address feedback

## Common Patterns

### Error Handling
- Use try/except blocks for I/O operations
- Log errors using the logger instance
- Graceful degradation when features fail

### Configuration
- Store settings in `systemConfig.py`
- Use SPI flash for persistent data
- Support over-the-air updates

### Web API
- RESTful-style endpoints in `backend.py`
- JSON for data exchange
- Minimal authentication (password protection available)

## Special Considerations

- **No external dependencies**: System must work offline (no cloud services)
- **Privacy-focused**: No data collection or phone home functionality
- **User control**: No automatic updates without permission
- **Reliability**: System should handle power loss gracefully
- **Debugging**: Use logger for development, minimize logging in production

## Resources

- Development setup: `dev/readme.md`
- FAQ & Troubleshooting: YouTube video and GitHub issues
- Contact: inventingfun@gmail.com
- Website: https://warpedpinball.com
