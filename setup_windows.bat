@echo off
REM ---------------------------------------------------------------------------
REM  TagForge - one time setup for Windows
REM  Creates a virtual environment and installs the dependencies.
REM  Double-click this file, or run it from a Command Prompt.
REM ---------------------------------------------------------------------------
setlocal

echo.
echo  == TagForge setup ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo  Python was not found on your PATH.
    echo  Install Python 3.10 or newer from https://www.python.org/downloads/
    echo  and tick "Add python.exe to PATH" during the installation.
    echo.
    pause
    exit /b 1
)

echo  Python found:
python --version
echo.

if not exist ".venv\" (
    echo  Creating the virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo  Could not create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo  Virtual environment .venv already exists - reusing it.
)

echo.
echo  Installing the dependencies (needs internet, one time only) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  The installation failed. Check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo  Setup finished. You can now start the app with run_app.bat
echo  or by typing:  .venv\Scripts\activate ^&^& streamlit run app.py
echo.
pause
