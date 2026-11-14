@echo off
rem Open the Droid Commander app: configure your droid and press LAUNCH! to start listening.
rem It reopens in the mode it was in when you closed it.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m droid app
