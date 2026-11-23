param([switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$studioUrl = 'http://127.0.0.1:8874/'
function Test-Studio {
    try {
        $response = Invoke-WebRequest -Uri $studioUrl -UseBasicParsing -TimeoutSec 2
        return ($response.Headers.Server -like 'CanvasGate/0.3*')
    } catch { return $false }
}
try {
    if (-not (Test-Studio)) {
        $pythonPath = (& python -c 'import sys; print(sys.executable)').Trim()
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
        $logDirectory = Join-Path $projectPath '.studio'
        New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
        $studioProcess = Start-Process -FilePath $pythonPath -ArgumentList '-m canvasgate.web --port 8874' -WorkingDirectory $projectPath -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory 'stdout.log') -RedirectStandardError (Join-Path $logDirectory 'stderr.log')
        $studioProcess.Id | Set-Content (Join-Path $logDirectory 'server.pid')
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            if (Test-Studio) { $ready = $true; break }
            if ($studioProcess.HasExited) { break }
            Start-Sleep -Milliseconds 300
        }
        if (-not $ready) { throw "Studio failed to start. See $logDirectory\stderr.log. Port 8874 may already be occupied." }
    }
    if (-not $NoOpen) { Start-Process $studioUrl }
    Write-Host "CanvasGate Studio: $studioUrl"
} catch {
    Write-Error $_
    exit 1
}
