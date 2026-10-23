[CmdletBinding()]
param(
    [ValidateSet('DEBUG', 'RELEASE')][string]$Target = 'DEBUG',
    [ValidateRange(1,128)][int]$Jobs = 4,
    [string]$Distribution = 'Debian'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$wsl = (Get-Command wsl.exe -ErrorAction Stop).Source
$linuxRoot = (& $wsl -d $Distribution --cd $projectRoot -- pwd).Trim()
if ($LASTEXITCODE -ne 0 -or -not $linuxRoot.StartsWith('/')) { throw 'WSL path lookup failed' }
& $wsl -d $Distribution -- bash "$linuxRoot/scripts/build.sh" $Target "$Jobs"
if ($LASTEXITCODE -ne 0) { throw "EDK2 build failed: $LASTEXITCODE" }
