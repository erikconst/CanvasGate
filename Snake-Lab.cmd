@echo off
setlocal
cd /d "%~dp0"
python -m canvasgate.snake_preview --open
pause
