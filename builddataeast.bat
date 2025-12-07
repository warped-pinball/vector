@echo off
REM Build and flash DataEast firmware using Python

IF EXIST build (
    echo Deleting build directory...
    rmdir /S /Q build
) ELSE (
    echo Build directory does not exist, skipping deletion.
)

REM Run the Python sync script for DataEast
python dev/sync.py data_east %1

REM Check for errors
IF %ERRORLEVEL% NEQ 0 (
    echo Sync script failed with error code %ERRORLEVEL%.
    exit /b %ERRORLEVEL%
) ELSE (
    echo Sync script completed successfully.
)