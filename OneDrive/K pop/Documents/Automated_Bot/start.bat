@echo off

:: Start ngrok with your Flask app
start ngrok http 5000

:: Wait for ngrok to initialize
timeout /t 5

:: Change directory to where your forex bot script is located
cd /d "Your file  path "

:: Start your Forex bot (Flask app or core trading logic)
python Forex_Swing_Bot.py

pause