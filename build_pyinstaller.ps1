param(
  [string]$Python = "python",
  [string]$Spec = "ultrabike.spec"
)

$ErrorActionPreference = "Stop"

Write-Host "Building UltraBike (PyInstaller)" -ForegroundColor Cyan

# Prefer the repo virtualenv by default to avoid permission issues with system Python.
if (-not $PSBoundParameters.ContainsKey('Python') -or $Python -eq 'python') {
  $venvPython = Join-Path (Get-Location) 'venv\Scripts\python.exe'
  if (Test-Path -LiteralPath $venvPython) {
    $Python = $venvPython
  }
}

# Ensure PyInstaller is installed in the active environment
${prevEap} = $ErrorActionPreference
try {
  # Native commands writing to stderr can trip $ErrorActionPreference='Stop'.
  $ErrorActionPreference = "Continue"
  & $Python -m pip show pyinstaller 1>$null 2>$null
} finally {
  $ErrorActionPreference = ${prevEap}
}

if ($LASTEXITCODE -ne 0) {
  Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
  & $Python -m pip install -U pyinstaller
}

# Build
& $Python -m PyInstaller --noconfirm --clean $Spec

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed"
}

Write-Host "Build complete." -ForegroundColor Green
Write-Host "Output: .\\dist\\UltraBike_Automatizacija.exe" -ForegroundColor Green

Write-Host "" 
Write-Host "Tip: to simulate a fresh install, run with a temporary data dir:" -ForegroundColor Cyan
Write-Host "  `$env:ULTRABIKE_DATA_DIR = (Resolve-Path .\\_fresh_data).Path" -ForegroundColor Cyan
Write-Host "  .\\dist\\UltraBike_Automatizacija.exe" -ForegroundColor Cyan
