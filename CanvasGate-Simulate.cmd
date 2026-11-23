@echo off
setlocal
cd /d "%~dp0"
python -m canvasgate examples/vault/CanvasGate/workflow.canvas --vault examples/vault --backend mock --output-dir examples/vault/CanvasGate/Runs
pause
