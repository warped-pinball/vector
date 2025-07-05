@echo off
REM Batch file to clean the build directory and run the build script for Windows

REM Check if the build directory exists
IF EXIST build (
    REM Remove the build directory and all its contents
    echo Deleting build directory...
    rmdir /S /Q build
) ELSE (
    echo Build directory does not exist, skipping deletion.
)

REM Run the Python build script
echo Running build script...
python dev/build.py --build-dir build/ --source-dir src/ --target_hardware sys11

REM Check for errors
IF %ERRORLEVEL% NEQ 0 (
    echo Build script failed with error code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
) ELSE (
    echo Build script completed successfully.
)
