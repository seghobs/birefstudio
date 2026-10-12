$ErrorActionPreference = 'SilentlyContinue'
$studioRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
$studioNext = Join-Path $studioRoot 'frontend\node_modules\next\dist\bin\next'
$snapshot = @(Get-CimInstance Win32_Process)
$targets = [Collections.Generic.HashSet[int]]::new()
foreach ($process in $snapshot) {
    $command = [string]$process.CommandLine
    $backend = $process.Name -eq 'python.exe' -and $command.Contains($studioPython) -and $command -match '\buvicorn\s+backend\.main:app\b'
    $frontend = $process.Name -eq 'node.exe' -and $command.Contains($studioNext)
    if (-not ($backend -or $frontend)) { continue }
    [void]$targets.Add([int]$process.ProcessId)
    # Stop the supervising launcher as well, so it does not report a server failure.
    $parentId = [int]$process.ParentProcessId
    for ($depth = 0; $depth -lt 3; $depth++) {
        $parent = $snapshot | Where-Object ProcessId -eq $parentId | Select-Object -First 1
        if (-not $parent) { break }
        if ($parent.Name -eq 'python.exe' -and $parent.CommandLine -match '\blauncher\.py(?:"|\s|$)') {
            [void]$targets.Add([int]$parent.ProcessId)
            break
        }
        $parentId = [int]$parent.ParentProcessId
    }
}
# Include wrapper workers and other children, using the captured process tree.
do {
    $changed = $false
    foreach ($process in $snapshot) {
        if ($targets.Contains([int]$process.ParentProcessId) -and $targets.Add([int]$process.ProcessId)) { $changed = $true }
    }
} while ($changed)
foreach ($targetId in $targets) {
    $original = $snapshot | Where-Object ProcessId -eq $targetId | Select-Object -First 1
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$targetId"
    # Avoid stopping an unrelated process if Windows has reused its PID.
    if ($current -and $current.CreationDate -eq $original.CreationDate) {
        Stop-Process -Id $targetId -Force
    }
}
