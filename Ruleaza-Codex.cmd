@echo off
setlocal
cd /d "%~dp0"
python -m canvasgate examples/vault/workflow.canvas --backend codex --max-calls 3 --output-dir examples/vault/Rezultate
pause
