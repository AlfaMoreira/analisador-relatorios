param([string]$Dist = 'dist')
$ErrorActionPreference = 'Stop'

function Invoke-CheckedProcess([string]$Executable, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Falha no processo de teste ($($process.ExitCode)): $Executable" }
}

# Este teste e executado somente no runner descartavel do GitHub, nunca no PC do usuario.
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'Teste de instalacao reservado ao runner descartavel do GitHub.' }
$destination = Join-Path $env:RUNNER_TEMP 'CelacantoInstalledTest'
if (-not ([System.IO.Path]::GetFullPath($destination).StartsWith(
    [System.IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase))) {
    throw 'A pasta de teste precisa permanecer dentro do RUNNER_TEMP.'
}
$smokeData = Join-Path $env:RUNNER_TEMP 'CelacantoInstalledSmoke'
$library = Join-Path $env:LOCALAPPDATA 'Celacanto/AnalisadorRelatorios'
$sentinel = Join-Path $library 'installer-test-preserve.txt'
New-Item -ItemType Directory -Path $library -Force | Out-Null
[System.IO.File]::WriteAllText($sentinel, 'Banco e historico nao pertencem a pasta do programa.')
$before = (Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash
$setup = (Resolve-Path -LiteralPath (Join-Path $Dist 'RevisorCelacanto-Instalador.exe')).Path
$arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', ('/DIR="' + $destination + '"'))
Invoke-CheckedProcess $setup $arguments
$shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'Revisor Celacanto.lnk'
if (-not (Test-Path -LiteralPath $shortcut)) { throw 'Atalho do menu Iniciar nao foi criado.' }
$program = Join-Path $destination 'RevisorCelacanto.exe'
Invoke-CheckedProcess $program @('--smoke', '--data-dir', ('"' + $smokeData + '"'))
# Reinstalacao por cima deve manter o programa funcional e preservar a biblioteca.
Invoke-CheckedProcess $setup $arguments
Invoke-CheckedProcess $program @('--smoke', '--data-dir', ('"' + $smokeData + '"'))
if ((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash -ne $before) { throw 'Biblioteca alterada pela instalacao.' }
Invoke-CheckedProcess (Join-Path $destination 'unins000.exe') @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
if (Test-Path -LiteralPath $program) { throw 'O programa permaneceu instalado apos a desinstalacao.' }
if (Test-Path -LiteralPath $shortcut) { throw 'O atalho permaneceu apos a desinstalacao.' }
if ((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash -ne $before) { throw 'Biblioteca alterada pela desinstalacao.' }
Write-Output 'Instalacao, reinstalacao, abertura e desinstalacao verificadas; biblioteca preservada.'
