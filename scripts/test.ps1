param(
  [string]$BuildDir = "build"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repo "artifacts\test-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMddTHHmmss"
$log = Join-Path $logDir "test-$timestamp.log"

Push-Location $repo
try {
  cmake --build $BuildDir --parallel 2 2>&1 | Tee-Object -FilePath $log
  if ($LASTEXITCODE -ne 0) { throw "build failed: $LASTEXITCODE" }
  ctest --test-dir $BuildDir --output-on-failure 2>&1 | Tee-Object -FilePath $log -Append
  if ($LASTEXITCODE -ne 0) { throw "CTest failed: $LASTEXITCODE" }
  $env:PYTHONPATH = Join-Path $repo "python"
  python -m unittest discover -s tests\python -v 2>&1 | Tee-Object -FilePath $log -Append
  if ($LASTEXITCODE -ne 0) { throw "Python tests failed: $LASTEXITCODE" }
} finally {
  Pop-Location
}

