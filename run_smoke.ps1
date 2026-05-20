$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = (Join-Path $projectRoot "src") + ";" + $env:PYTHONPATH

Push-Location $projectRoot
try {
    conda run -n 5AxisSlicer python tools\smoke_core.py
}
finally {
    Pop-Location
}
