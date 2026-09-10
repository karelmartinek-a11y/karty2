$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if ($env:OS -ne 'Windows_NT') { throw 'Build vyžaduje Windows x64 a Python 3.12 x64.' }
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Vytvoření prostředí selhalo.' }
& .\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
if ($LASTEXITCODE -ne 0) { throw 'Instalace zamčených závislostí selhala.' }
& .\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) { throw 'Instalace projektu selhala.' }
& .\.venv\Scripts\python.exe -m pytest -q --junitxml=docs\windows-test-results.xml
if ($LASTEXITCODE -ne 0) { throw 'Testy selhaly; build zastaven.' }
& .\.venv\Scripts\python.exe tools\collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'Sběr licencí selhal.' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean KajovoKarty.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller selhal.' }
$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (!$compiler) {
    $compilerPath = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    if (!(Test-Path $compilerPath)) { throw 'Chybí Inno Setup 6. Onedir aplikace je v dist\KajovoKarty.' }
} else { $compilerPath = $compiler.Source }
& $compilerPath tools\installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Vytvoření instalátoru selhalo.' }
Get-FileHash dist\installer\KajovoKarty-Setup-0.3.1.exe -Algorithm SHA256 | Format-List | Out-File docs\windows-installer-sha256.txt
