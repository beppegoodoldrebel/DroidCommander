# Build Droid Commander: the app folder (PyInstaller) and the installer (Inno Setup).
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# Output:  dist\DroidCommander\          the app (two .exe + support files)
#          dist\DroidCommander-Setup-<version>.exe   the installer
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
$version = & $py -c "import droid; print(droid.__version__)"
Write-Host "== Droid Commander $version"

Write-Host "== icon and licenses"
& $py packaging\make_icon.py
& $py packaging\collect_licenses.py

Write-Host "== PyInstaller"
& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\DroidCommander.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { Write-Warning "Inno Setup 6 not found: the app is in dist\DroidCommander, no installer built."; exit 0 }
Write-Host "== Inno Setup"
& $iscc "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "== done: dist\DroidCommander-Setup-$version.exe"
