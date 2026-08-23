param(
  [string]$VenvDir = ".venv_build",
  [string]$Spec = "ultrabike.spec",
  [string]$DistDir = "dist",
  [string]$WorkDir = "build"
)

$ErrorActionPreference = "Stop"

Write-Host "Building UltraBike (PyInstaller, clean venv)" -ForegroundColor Cyan

function Remove-WithRetry {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [int]$Attempts = 6,
    [int]$DelayMs = 700
  )

  for ($i = 1; $i -le $Attempts; $i++) {
    try {
      if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Force -Recurse -ErrorAction Stop
      }
      return
    } catch {
      if ($i -eq $Attempts) { throw }
      Start-Sleep -Milliseconds $DelayMs
    }
  }
}

# If a previous build is still running, PyInstaller can't overwrite the exe.
try {
  $running = Get-Process -Name "UltraBike_Automatizacija" -ErrorAction SilentlyContinue
  foreach ($p in $running) {
    try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch { }
  }
} catch { }

# Best-effort cleanup of previous outputs (handles file locks with retries)
Remove-WithRetry -Path (Join-Path $DistDir "UltraBike_Automatizacija.exe")
Remove-WithRetry -Path $DistDir
Remove-WithRetry -Path $WorkDir

# Create isolated build env to avoid bundling unrelated globally-installed packages
if (-not (Test-Path $VenvDir)) {
  python -m venv $VenvDir
}

$py = Join-Path $VenvDir "Scripts\python.exe"

& $py -m pip install -U pip wheel
& $py -m pip install -r requirements.txt
& $py -m pip install -U pyinstaller

# Ensure user-site packages are ignored during analysis
$env:PYTHONNOUSERSITE = "1"

& $py -m PyInstaller --noconfirm --clean --distpath $DistDir --workpath $WorkDir $Spec
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed"
}

Write-Host "Build complete." -ForegroundColor Green
Write-Host ("Output: .\\{0}\\UltraBike_Automatizacija.exe" -f $DistDir) -ForegroundColor Green

$builtExe = Join-Path $DistDir "UltraBike_Automatizacija.exe"
$smoke = Start-Process -FilePath $builtExe -ArgumentList "--smoke-test" -Wait -PassThru -WindowStyle Hidden
if ($smoke.ExitCode -ne 0) {
  throw "Packaged smoke test failed with exit code $($smoke.ExitCode)"
}
Write-Host "Packaged smoke test passed." -ForegroundColor Green
