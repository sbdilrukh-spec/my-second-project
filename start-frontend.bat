@echo off
echo ========================================
echo   ОНД-86 — Запуск Frontend (React)
echo ========================================
cd /d "%~dp0frontend"

:: Добавляем Node.js в PATH на случай если не прописан
set PATH=%PATH%;C:\Program Files\nodejs

if not exist "node_modules" (
    echo Установка npm-пакетов...
    npm install
)

echo.
echo Frontend запускается на http://localhost:5173
echo.
npm run dev
pause
