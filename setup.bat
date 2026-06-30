@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === Check Tham Gia - Cai dat ===

where py >nul 2>&1
if %errorlevel%==0 (
    set PY=py
) else (
    set PY=python
)

echo Dung lenh: %PY%
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt

if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo.
        echo ========================================
        echo  QUAN TRONG: Mo file .env va dien:
        echo    BOT_TOKEN  - lay tu @BotFather
        echo    ADMIN_IDS  - lay tu @userinfobot
        echo ========================================
        echo.
    )
) else (
    echo File .env da ton tai - kiem tra BOT_TOKEN da dung chua
)

echo.
echo === Xong! Chay: run.bat hoac %PY% main.py ===
pause
