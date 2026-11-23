@echo off
setlocal
cd /d "%~dp0"
python -m canvasgate examples/vault/workflow.canvas --backend mock --output-dir examples/vault/Rezultate
pause
