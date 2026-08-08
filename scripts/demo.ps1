$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$processes = @()

try {
    $processes += Start-Process -FilePath 'uv' -ArgumentList @('run', 'uvicorn', 'demo_target.api:app', '--port', '8082') -WorkingDirectory $workspace -PassThru -WindowStyle Hidden
    $processes += Start-Process -FilePath 'uv' -ArgumentList @('run', 'uvicorn', 'drift.api:app', '--port', '8080') -WorkingDirectory $workspace -PassThru -WindowStyle Hidden
    $processes += Start-Process -FilePath 'npm' -ArgumentList @('run', 'dev') -WorkingDirectory (Join-Path $workspace 'web') -PassThru -WindowStyle Hidden

    Write-Output 'Drift local demo is starting.'
    Write-Output 'Operations Room: http://localhost:5173'
    Write-Output 'API docs:       http://localhost:8080/docs'
    Write-Output 'Replay target:  http://localhost:8082/healthz'
    Write-Output 'Press Ctrl+C to stop all three processes.'

    while ($true) { Start-Sleep -Seconds 2 }
}
finally {
    foreach ($process in $processes) {
        if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    }
}
