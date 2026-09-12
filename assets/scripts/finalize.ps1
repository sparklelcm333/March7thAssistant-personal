# finalize.ps1 - M7A 更新执行器（外置，运行在 temp，不在被更新目录）
#
# 职责：等主程序退出 -> 杀辅助进程 -> 用 hpatchz 应用补丁（temp 副本，避免自锁）
#       -> 成功启动新版本 / 失败重启旧版本（原子回滚后旧版完好，下次更新重试）。
#
# 不做 temp 清理：残留由主程序启动时统一清空（apply.cleanup_temp_residue），
# 本脚本只负责执行阶段，单一职责。
#
# 参数：
#   -WaitPid <pid>      主程序 PID，等待其退出
#   -Patch   <path>     hpatchz 补丁文件路径（zstd 压缩、无后缀，hpatchz 自动解压）
#   -Target  <path>     应用目录（补丁的 oldDir == outNewDir，原地应用）
#
# 运行位置在 temp：所有待更新文件（应用目录内）patch 时均无锁，所有运行中执行体
# （本脚本 / hpatchz 副本）都在 temp，不在补丁清单内。

param(
    [int]$WaitPid,
    [string]$Patch,
    [string]$Target,
    [switch]$StartMinimized
)

$ErrorActionPreference = "Stop"

# 需要终止的辅助进程名（执行器唯一源，Python 侧不再维护同名单）
$ProcessNames = @(
    "March7thAssistant.exe",
    "flet.exe",
    "gui.exe",
    "Fhoe-Rail.exe",
    "chromedriver.exe",
    "PaddleOCR-json.exe"
)

# 本脚本所在目录（temp）
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HPatchZ = Join-Path $ScriptDir "hpatchz.exe"
$LogDir = Join-Path $Target "logs"

function Write-Log([string]$Message) {
    try {
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }
        $LogFile = Join-Path $LogDir ("{0:yyyy-MM-dd}.log" -f (Get-Date))
        $Line = "[{0:HH:mm:ss}] {1}" -f (Get-Date), $Message
        Add-Content -Path $LogFile -Value $Line -Encoding UTF8
    } catch {
        # 日志失败不影响更新主流程
    }
}

function Start-MainProgram {
    # 启动主程序（当前构建产物 March7thAssistant.exe）。Start-Process 本身即分离进程。
    $launcher = Join-Path $Target "March7thAssistant.exe"
    if (Test-Path $launcher) {
        $argList = @()
        if ($StartMinimized) { $argList += "--start-minimized-to-tray" }
        Start-Process -FilePath $launcher -WorkingDirectory $Target -ArgumentList $argList
        return $true
    }
    Write-Log "ERROR: 未找到可启动的主程序"
    return $false
}

function Restart-OldVersion {
    # 补丁失败：旧版本完好（原子回滚），重启旧主程序，下次更新重试
    Start-MainProgram | Out-Null
}

function Stop-RelatedProcesses {
    foreach ($name in $ProcessNames) {
        Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($name)) -ErrorAction SilentlyContinue |
            ForEach-Object {
                Write-Log "KILL: $($_.Name) (PID=$($_.Id))"
                try {
                    Stop-Process -Id $_.Id -Force -ErrorAction Stop
                } catch {
                    Write-Log "WARN: 无法终止 $($_.Name) PID=$($_.Id): $($_.Exception.Message)"
                }
            }
    }
}

Write-Log "finalize 启动: WaitPid=$WaitPid Patch=$Patch Target=$Target"

# 1. 等待主程序退出
if ($WaitPid -gt 0) {
    $waited = $false
    for ($i = 0; $i -lt 150; $i++) {
        $proc = Get-Process -Id $WaitPid -ErrorAction SilentlyContinue
        if (-not $proc) {
            $waited = $true
            break
        }
        Start-Sleep -Milliseconds 200
    }
    if (-not $waited) {
        Write-Log "WARN: 等待主程序退出超时(30s)，继续处理"
    }
}

# 2. 杀掉辅助进程
Stop-RelatedProcesses

# 3. 应用补丁（hpatchz 从 temp 运行，避免应用目录内 hpatchz.exe 自锁）
if (-not (Test-Path $HPatchZ)) {
    Write-Log "ERROR: 未找到 hpatchz 副本: $HPatchZ"
    Restart-OldVersion
    exit 1
}
if (-not (Test-Path $Patch)) {
    Write-Log "ERROR: 未找到补丁文件: $Patch"
    Restart-OldVersion
    exit 1
}

Write-Log "hpatchz 应用补丁: $Target <- $Patch"
# 注意：PowerShell 5.1 下 $ErrorActionPreference=Stop 会把外部命令（hpatchz）的
# stderr + 非零退出码当作终止错误中断脚本——导致退出码日志不写、重启逻辑不执行。
# 这里临时切回 Continue，用 $LASTEXITCODE 显式判断成败。
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$Output = & $HPatchZ -f -C-new $Target $Patch $Target 2>&1
$ExitCode = $LASTEXITCODE
$ErrorActionPreference = $oldEAP
if ($Output) {
    Write-Log "hpatchz 输出: $($Output | Out-String)"
}
Write-Log "hpatchz 退出码: $ExitCode"

if ($ExitCode -eq 0) {
    # 4. 成功：启动新版本
    Write-Log "补丁应用成功，启动新版本"
    Start-MainProgram | Out-Null
} else {
    # 5. 失败：原子回滚保证旧版完好，重启旧版重试
    Write-Log "ERROR: 补丁应用失败(退出码=$ExitCode)，重启旧版本"
    Restart-OldVersion
}

exit $ExitCode
