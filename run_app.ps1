$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = (Join-Path $projectRoot "src") + ";" + $env:PYTHONPATH

Push-Location $projectRoot
try {
    conda run -n 5AxisSlicer python -m five_axis_slicer
}
finally {
    Pop-Location
}
