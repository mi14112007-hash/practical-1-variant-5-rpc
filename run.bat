@echo off
cd /d "%~dp0"
python -m src.cli %*
exit /b %errorlevel%
