@echo off
echo ==========================================
echo    Instagram Chatbot - Admin Panel
echo ==========================================
echo.

cd /d "%~dp0backend"

if not exist ".env" (
    echo .env fayli topilmadi! .env.example dan nusxa olinmoqda...
    copy .env.example .env
    echo .env fayli yaratildi. Iltimos, .env faylini tahrirlang!
    notepad .env
    pause
)

echo Kutubxonalar o'rnatilmoqda...
pip install -r requirements.txt -q

echo.
echo Server ishga tushmoqda...
echo Admin Panel: http://localhost:8000
echo Webhook URL: http://localhost:8000/webhook
echo.
python main.py
pause
