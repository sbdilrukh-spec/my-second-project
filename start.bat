@echo off
echo ========================================
echo   ОНД-86 — Запуск приложения
echo ========================================

:: Запуск Backend в отдельном окне
start "OND86-Backend" cmd /c "cd /d "%~dp0backend" && venv\Scripts\activate && python run.py"

:: Небольшая пауза чтобы backend успел стартовать
timeout /t 3 /nobreak >nul

:: Запуск Frontend в отдельном окне
start "OND86-Frontend" cmd /c "cd /d "%~dp0frontend" && npm run dev"

:: Пауза чтобы frontend успел стартовать
timeout /t 4 /nobreak >nul

:: Открываем браузер
start http://localhost:5173

echo.
echo Приложение запущено!
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo.
echo Чтобы остановить — закрой окна OND86-Backend и OND86-Frontend.
