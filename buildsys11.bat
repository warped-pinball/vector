@echo off
REM Build and flash System 11 firmware using Python

IF EXIST build (
    echo Deleting build directory...
    rmdir /S /Q build
) ELSE (
    echo Build directory does not exist, skipping deletion.
)

REM Run the Python sync script
python dev/sync.py sys11 %1

REM Check for errors
IF %ERRORLEVEL% NEQ 0 (
    echo Sync script failed with error code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
) ELSE (
    echo Sync script completed successfully.
)
