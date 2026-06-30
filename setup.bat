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
        echo Da tao file .env - hay sua BOT_TOKEN, API_ID, API_HASH, ADMIN_IDS
    )
) else (
    echo File .env da ton tai
)

echo.
echo === Xong! Chay: run.bat hoac %PY% main.py ===
pause
