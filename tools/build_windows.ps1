$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
if ($env:OS -ne 'Windows_NT') { throw 'Build vyžaduje Windows x64 a Python 3.12 x64.' }
$buildEnvironment = Join-Path $PWD '.tmp\build-venv'
$buildPython = Join-Path $buildEnvironment 'Scripts\python.exe'
if (!(Test-Path -LiteralPath $buildPython)) {
    py -3.12 -m venv $buildEnvironment
    if ($LASTEXITCODE -ne 0) { throw 'Vytvoření prostředí selhalo.' }
}
& $buildPython -c "import sys, struct; assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8"
if ($LASTEXITCODE -ne 0) { throw 'Build vyžaduje Python 3.12 x64.' }
& $buildPython -m pip install --require-hashes -r requirements-dev.lock
if ($LASTEXITCODE -ne 0) { throw 'Instalace zamčených závislostí selhala.' }
& $buildPython -m pip install --no-deps --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) { throw 'Instalace projektu selhala.' }
$appVersion = & $buildPython -c 'from kajovokarty import __version__; print(__version__)'
if ($LASTEXITCODE -ne 0) { throw 'Nelze zjistit verzi aplikace.' }
& $buildPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Nekonzistentní závislosti.' }
& $buildPython -m ruff check src tests tools --select F --no-cache
if ($LASTEXITCODE -ne 0) { throw 'Statická kontrola selhala.' }
& $buildPython tools\error_catalog.py --check
if ($LASTEXITCODE -ne 0) { throw 'Katalog chyb není aktuální.' }
& $buildPython -m pytest -q -p no:cacheprovider "--junitxml=docs/audit-$appVersion-tests.xml"
if ($LASTEXITCODE -ne 0) { throw 'Testy selhaly; build zastaven.' }
& $buildPython tools\collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'Sběr licencí selhal.' }
& $buildPython -m PyInstaller --noconfirm --clean KajovoKarty.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller selhal.' }
& $buildPython tools\verify_frozen.py dist\KajovoKarty\KajovoKarty.exe --output "docs/audit-$appVersion-frozen-code.json"
if ($LASTEXITCODE -ne 0) { throw 'Sestavený kód neodpovídá zdrojům.' }
$qaDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ('kajovokarty-build-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $qaDirectory | Out-Null
$qaReportPath = Join-Path $qaDirectory 'frozen-smoke.json'
$previousPlatform = $env:QT_QPA_PLATFORM
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $qaProcess = Start-Process -FilePath (Join-Path $PWD 'dist\KajovoKarty\KajovoKarty.exe') -ArgumentList @('--self-test-report', ('"' + $qaReportPath + '"')) -WindowStyle Hidden -PassThru
    if (!$qaProcess.WaitForExit(60000)) {
        Stop-Process -Id $qaProcess.Id
        throw 'Časový limit distribučního self-testu.'
    }
    if ($qaProcess.ExitCode -ne 0) { throw "Distribuční self-test selhal; protokol: $qaReportPath" }
    $qaResult = Get-Content -LiteralPath $qaReportPath -Raw | ConvertFrom-Json
    if ($qaResult.status -ne 'PASS' -or !$qaResult.frozen -or $qaResult.version -ne $appVersion) { throw 'Neplatný protokol self-testu.' }
    Copy-Item -LiteralPath $qaReportPath -Destination "docs/audit-$appVersion-frozen.json"
    Write-Output "Self-test PASS; renderované snímky: $qaDirectory"
} finally { $env:QT_QPA_PLATFORM = $previousPlatform }
$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (!$compiler) {
    $compilerCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    )
    $compilerPath = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (!$compilerPath) { throw 'Chybí Inno Setup 6. Onedir aplikace je v dist\KajovoKarty.' }
} else { $compilerPath = $compiler.Source }
& $compilerPath tools\installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Vytvoření instalátoru selhalo.' }
Get-FileHash "dist/installer/KajovoKarty-Setup-$appVersion.exe" -Algorithm SHA256 | Format-List | Out-File "docs/audit-$appVersion-installer-sha256.txt"
