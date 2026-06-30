@echo off
chcp 65001 >nul
echo ========================================
echo  UpBain v26 — fix TypeError pinned msg
echo ========================================
echo.

if not exist "core" (
    echo ❌ Chạy file này TRONG thư mục UpBain ^(cùng cấp tool__tauto_nostage.py^)
    pause
    exit /b 1
)

set PATCH=%~dp0core

if not exist "%PATCH%\forum_api.py" (
    echo ❌ Không tìm thấy patch. Pull branch cursor/fix-upbain-pinned-typeerror-9fbc
    pause
    exit /b 1
)

copy /Y "%PATCH%\forum_api.py" "core\forum_api.py"
copy /Y "%PATCH%\pin_manager.py" "core\pin_manager.py"
copy /Y "%PATCH%\source_collector.py" "core\source_collector.py"

echo.
echo ✅ Đã copy 3 file vào core\
echo    - forum_api.py ^(mới^)
echo    - pin_manager.py
echo    - source_collector.py
echo.
echo Tắt tool rồi chạy lại.
pause
