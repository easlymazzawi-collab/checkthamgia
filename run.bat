@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
    set PY=py
) else (
    set PY=python
)

if not exist .env (
    echo Chua co file .env - chay setup.bat truoc
    pause
    exit /b 1
)

%PY% -c "import aiogram" 2>nul
if errorlevel 1 (
    echo Chua cai thu vien - chay setup.bat truoc
    pause
    exit /b 1
)

echo Dang chay bot...
%PY% main.py
pause
