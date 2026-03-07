@echo off
echo ========================================
echo   ОНД-86 — Запуск Backend (FastAPI)
echo ========================================
cd /d "%~dp0backend"

:: Проверяем наличие виртуального окружения
if not exist "venv\Scripts\activate.bat" (
    echo Создание виртуального окружения...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Установка зависимостей...
pip install -r requirements.txt -q

echo.
echo Backend запускается на http://localhost:8000
echo Документация API: http://localhost:8000/docs
echo.
python run.py
pause
