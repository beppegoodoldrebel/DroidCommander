@echo off
rem Start Droid Commander in a console window (no GUI). Close this window or press Ctrl+C to quit.
cd /d "%~dp0"
title Droid Commander (console)
".venv\Scripts\python.exe" -m droid -v
pause
