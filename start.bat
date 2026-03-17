@echo off
echo ========================================
echo   ОНД-86 — Запуск приложения
echo ========================================

:: Запуск Backend в отдельном окне
start "ОНД-86 Backend" cmd /k "cd /d "%~dp0backend" && venv\Scripts\activate && python run.py"

:: Небольшая пауза чтобы backend успел стартовать
timeout /t 3 /nobreak >nul

:: Запуск Frontend в отдельном окне
start "ОНД-86 Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

:: Пауза чтобы frontend успел стартовать
timeout /t 4 /nobreak >nul

:: Открываем браузер
start http://localhost:5173

echo.
echo Приложение запускается...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo.
echo Не закрывай окна Backend и Frontend!
