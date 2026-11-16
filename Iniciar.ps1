$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$venvDir = Join-Path $env:LOCALAPPDATA 'Celacanto\ar-venv'
$pythonExe = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    py -3.12 -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw 'Instale o Python 3.12 para continuar.' }
}
& $pythonExe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'A instalação das dependências falhou. Confira sua conexão e execute novamente.' }
& $pythonExe -m revisor @args
