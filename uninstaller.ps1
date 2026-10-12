param([switch]$ConfirmRemoval, [switch]$WhatIf, [switch]$NoPause)
$ErrorActionPreference = 'Stop'
$studioRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$prefix = $studioRoot + '\'

function Assert-StudioPath([string]$path) {
    $absolute = [IO.Path]::GetFullPath($path)
    if (-not $absolute.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) {
        throw "Proje disindaki yol reddedildi: $absolute"
    }
    return $absolute
}

function Remove-StudioTree([string]$path) {
    $absolute = Assert-StudioPath $path
    if (-not (Test-Path -LiteralPath $absolute)) { return }
    # Walk explicitly: never recurse through a junction/symlink into other data.
    $item = Get-Item -LiteralPath $absolute -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        if ($item.PSIsContainer) { [IO.Directory]::Delete($absolute) }
        else { [IO.File]::Delete($absolute) }
        return
    }
    if (-not $item.PSIsContainer) { Remove-Item -LiteralPath $absolute -Force; return }
    foreach ($child in Get-ChildItem -LiteralPath $absolute -Force) {
        Remove-StudioTree $child.FullName
    }
    Remove-Item -LiteralPath $absolute -Force
}

try {
    if ($studioRoot -eq [IO.Path]::GetPathRoot($studioRoot).TrimEnd('\') -or
        -not (Test-Path -LiteralPath (Join-Path $studioRoot 'launcher.py')) -or
        -not (Test-Path -LiteralPath (Join-Path $studioRoot 'frontend\package.json'))) {
        throw 'BiRef Studio proje klasoru dogrulanamadi. Kaldirma iptal edildi.'
    }
    $relativeTargets = @('.venv','venv','.tools','frontend\node_modules','frontend\.next',
                         'frontend\tsconfig.tsbuildinfo','data','logs','uploads','input','output',
                         'teslim','gfpgan','.pytest_cache','__pycache__','backend\__pycache__',
                         'backend\tests\__pycache__')
    $targets = @($relativeTargets | ForEach-Object { Assert-StudioPath (Join-Path $studioRoot $_) })
    Write-Host 'BiRef Studio - Uygulamayi kaldir' -ForegroundColor Yellow
    Write-Host 'Backend/frontend kapatilacak. Yerel ortamlar, paketler, modeller,'
    Write-Host 'YUKLENEN FOTOGRAFLAR, SONUCLAR ve teslim dosyalari kalici silinecek.'
    Write-Host 'Kaynak kodu ve Git kayitlari korunur; setup.bat ile tekrar kurulabilir.'
    Write-Host 'Onceden kurulu sistem Python/Node.js ve diger projeler silinmez.'
    if ($env:STUDIO_DATA_DIR) {
        $custom = [IO.Path]::GetFullPath($env:STUDIO_DATA_DIR)
        if ($custom.TrimEnd('\') -ne (Join-Path $studioRoot 'data')) {
            Write-Host "Ozel veri yolu otomatik silinmez: $custom" -ForegroundColor Yellow
        }
    }
    if ($WhatIf) {
        $targets | ForEach-Object { Write-Host "[Onizleme] $_" }
        exit 0
    }
    if (-not $ConfirmRemoval) {
        $answer = Read-Host 'Kalici silmeyi onaylamak icin KALDIR yazin'
        if ($answer -cne 'KALDIR') { Write-Host 'Kaldirma iptal edildi.'; exit 0 }
    }
    $stopScript = Join-Path $studioRoot 'stop.ps1'
    if (-not (Test-Path -LiteralPath $stopScript)) { throw 'stop.ps1 bulunamadi; silme yapilmadi.' }
    & $stopScript
    $ErrorActionPreference = 'Stop'
    # Remove this setup's private Python installer registration as well as files.
    # Never invoke it against a pre-existing or subsequently relocated Python.
    $privatePython = Join-Path $studioRoot '.tools\python'
    $pythonKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software\Python\PythonCore\3.13\InstallPath')
    $installedPath = if ($pythonKey) { $pythonKey.GetValue('') } else { $null }
    if ($pythonKey) { $pythonKey.Close() }
    if ($installedPath -and [IO.Path]::GetFullPath($installedPath).TrimEnd('\') -eq $privatePython) {
        $installer = Assert-StudioPath (Join-Path $studioRoot '.tools\python-3.13.16-amd64.exe')
        if (-not (Test-Path -LiteralPath $installer)) { throw 'Ozel Python kaldirma paketi eksik. Once setup.bat ile onarin.' }
        $expectedHash = 'fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b'
        if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
            throw 'Python kaldirma paketi dogrulanamadi.'
        }
        $removal = Start-Process -FilePath $installer -ArgumentList '/uninstall','/quiet' -WindowStyle Hidden -Wait -PassThru
        if ($removal.ExitCode -notin @(0,3010)) { throw "Ozel Python kaldirilamadi (kod: $($removal.ExitCode))." }
    }
    $failures = @()
    foreach ($target in $targets) {
        try {
            Remove-StudioTree $target
            Write-Host "Temizlendi: $($target.Substring($prefix.Length))"
        } catch { $failures += "$target : $($_.Exception.Message)" }
    }
    if ($failures.Count) { throw ($failures -join "`n") }
    Write-Host 'Uygulama kurulumu ve yerel verileri kaldirildi.' -ForegroundColor Green
    if (-not $NoPause) { Read-Host 'Pencereyi kapatmak icin Enter' | Out-Null }
    exit 0
} catch {
    Write-Host ("HATA: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Kilitli dosya varsa kurulum pencerelerini kapatip tekrar deneyin.'
    if (-not $NoPause) { Read-Host 'Pencereyi kapatmak icin Enter' | Out-Null }
    exit 1
}
