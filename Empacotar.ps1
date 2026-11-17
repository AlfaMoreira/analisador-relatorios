$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$buildRoot = Join-Path $env:LOCALAPPDATA 'Celacanto\build'
$venvDir = Join-Path $env:LOCALAPPDATA 'Celacanto\ar-venv'
$pythonExe = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    py -3.12 -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 não disponível.' }
}
& $pythonExe -m pip install -r requirements.txt pyinstaller==6.22.3
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências.' }
New-Item -ItemType Directory -Force $buildRoot | Out-Null
& $pythonExe build_windows.py --distpath dist --workpath $buildRoot
if ($LASTEXITCODE -ne 0) { throw 'Falha no empacotamento Windows.' }
Write-Host 'Executável disponível em dist\RevisorCelacanto\RevisorCelacanto.exe. Distribua a pasta inteira.'
