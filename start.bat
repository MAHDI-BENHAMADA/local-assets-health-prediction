@echo off
echo Starting Device Health Monitor Server...
start "" python server.py

echo Waiting for server to initialize...
timeout /t 3 /nobreak > NUL

echo Starting Collector Loop...
:loop
python collector.py
echo.
echo Waiting 5 seconds before next collection...
timeout /t 5 /nobreak > NUL
goto loop
