@echo off
cd /d "%~dp0"

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
) else (
    call venv\Scripts\activate.bat
)

python -c "import flask, dotenv, requests, youtube_transcript_api, openpyxl, reportlab" >nul 2>&1
if errorlevel 1 (
    echo Installing or updating dependencies...
    python -m pip install -r requirements.txt
)

echo.
echo ============================================
echo   YouTube Analyzer  ->  http://127.0.0.1:5002
echo   (Press CTRL+C to stop)
echo ============================================
echo.
python app.py
pause
