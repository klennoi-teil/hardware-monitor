param(
    [switch]$Agent,
    [switch]$Gui,
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status
)

$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Install) {
    & $py "$dir\monitor_agent.py" --install
} elseif ($Uninstall) {
    & $py "$dir\monitor_agent.py" --uninstall
} elseif ($Status) {
    & $py "$dir\monitor_agent.py" --status
} elseif ($Agent) {
    & $py "$dir\monitor_agent.py" @args
} elseif ($Gui) {
    & $py "$dir\main.py" --gui @args
} else {
    & $py "$dir\main.py" @args
}
