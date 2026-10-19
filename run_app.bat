@echo off
REM ---------------------------------------------------------------------------
REM  TagForge - start the app
REM  Run setup_windows.bat once before using this file.
REM  The app opens at http://localhost:8501
REM  Press Ctrl+C in this window to stop it.
REM ---------------------------------------------------------------------------
setlocal

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  The virtual environment is missing.
    echo  Run setup_windows.bat first.
    echo.
    pause
    exit /b 1
)

echo.
echo  Starting TagForge ... (press Ctrl+C to stop)
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless false

pause
