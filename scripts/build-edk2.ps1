[CmdletBinding()]
param(
    [ValidateSet('DEBUG', 'RELEASE')][string]$Target = 'DEBUG',
    [ValidateRange(1,128)][int]$Jobs = 4,
    [ValidateSet('NORMAL', 'SHELL_QEMU', 'SEC_VISUAL', 'GOP_MODEL', 'SEC_C', 'SEC_MEM', 'SEC_STACK', 'SEC_MMU', 'SEC_DXE', 'DXE_MEM', 'DXE_GCD', 'DXE_TABLES', 'DXE_DEBUG', 'DXE_DISPATCH', 'DXE_GOP', 'DXE_TEXT', 'DXE_APP', 'UFS_HANDOFF', 'UFS_QUEUES', 'UFS_LK_MAP', 'UFS_NOP11', 'UFS_DATA')][string]$Mode = 'NORMAL',
    [string]$Distribution = 'Debian'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$wsl = (Get-Command wsl.exe -ErrorAction Stop).Source
$linuxRoot = (& $wsl -d $Distribution --cd $projectRoot -- pwd).Trim()
if ($LASTEXITCODE -ne 0 -or -not $linuxRoot.StartsWith('/')) { throw 'WSL path lookup failed' }
& $wsl -d $Distribution -- bash "$linuxRoot/scripts/build.sh" $Target "$Jobs" $Mode
if ($LASTEXITCODE -ne 0) { throw "EDK2 build failed: $LASTEXITCODE" }
