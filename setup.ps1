param([switch]$NoPause, [switch]$SkipModels)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$studioRoot = $PSScriptRoot
$toolsRoot = Join-Path $studioRoot '.tools'
New-Item -ItemType Directory -Force -Path (Join-Path $studioRoot 'logs') | Out-Null

function Find-StudioPython {
    $candidates = @((Join-Path $studioRoot '.venv\Scripts\python.exe'),
                    (Join-Path $toolsRoot 'python\python.exe'))
    foreach ($commandName in @('python.exe','python3.exe')) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command -and $command.Source -notlike '*\WindowsApps\*') { $candidates += $command.Source }
    }
    foreach ($version in @('312','313')) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe"
    }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate)) { continue }
        $probe = & $candidate -c 'import sys,struct; print(int((3,12)<=sys.version_info[:2]<(3,14) and struct.calcsize(chr(80))==8))'
        if ($LASTEXITCODE -eq 0 -and $probe -eq '1') { return $candidate }
    }
    return $null
}

function Find-StudioNode {
    $candidates = @((Join-Path $toolsRoot 'node\node.exe'))
    $command = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    $candidates += Join-Path $env:ProgramFiles 'nodejs\node.exe'
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate)) { continue }
        $probe = & $candidate --version
        $npm = Join-Path (Split-Path $candidate) 'npm.cmd'
        if ($LASTEXITCODE -eq 0 -and $probe -match '^v(22|24)\.' -and (Test-Path -LiteralPath $npm)) { return $candidate }
    }
    return $null
}

try {
    Start-Transcript -Path (Join-Path $studioRoot 'logs\setup.log') -Append | Out-Null
    Set-Location -LiteralPath $studioRoot
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        throw 'Bu kurulum Windows x64 gerektirir.'
    }
    Write-Host 'BiRef Studio - Otomatik kurulum' -ForegroundColor Green
    Write-Host 'Ilk kurulumda internet ve modeller icin birkac GB bos alan gerekir.'
    $pythonPath = Find-StudioPython
    if (-not $pythonPath) {
        Write-Host '[1/4] Python indiriliyor ve otomatik kuruluyor...'
        New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
        $installer = Join-Path $toolsRoot 'python-3.13.16-amd64.exe'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.exe' -OutFile $installer
        $expected = 'fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b'
        if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
            throw 'Python indirme dogrulamasi basarisiz. setup.bat dosyasini tekrar acin.'
        }
        $pythonTarget = Join-Path $toolsRoot 'python'
        $installArgs = @('/quiet','InstallAllUsers=0','Include_launcher=0','PrependPath=0',
                         'Include_test=0','Include_doc=0','Include_tcltk=0','Include_pip=1',
                         ('TargetDir="' + $pythonTarget + '"'))
        $installation = Start-Process -FilePath $installer -ArgumentList $installArgs -WindowStyle Hidden -Wait -PassThru
        if ($installation.ExitCode -notin @(0,3010)) { throw "Python kurulamadi (kod: $($installation.ExitCode))." }
        $pythonPath = Find-StudioPython
        if (-not $pythonPath) { throw 'Python kuruldu ancak calistirilamadi.' }
    } else { Write-Host '[1/4] Uyumlu Python bulundu.' }

    $nodePath = Find-StudioNode
    if (-not $nodePath) {
        Write-Host '[2/4] Node.js 24 LTS indiriliyor ve hazirlaniyor...'
        New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
        $baseUrl = 'https://nodejs.org/dist/latest-v24.x/'
        $checksums = (Invoke-WebRequest -UseBasicParsing -Uri ($baseUrl+'SHASUMS256.txt')).Content
        $match = [regex]::Match([string]$checksums,'(?m)^([a-f0-9]{64})\s+(node-v24\.\d+\.\d+-win-x64\.zip)\s*$')
        if (-not $match.Success) { throw 'Resmi Node.js paket bilgisi alinamadi.' }
        $archive = Join-Path $toolsRoot $match.Groups[2].Value
        Invoke-WebRequest -UseBasicParsing -Uri ($baseUrl+$match.Groups[2].Value) -OutFile $archive
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $match.Groups[1].Value) {
            throw 'Node.js indirme dogrulamasi basarisiz.'
        }
        $unpackRoot = Join-Path $toolsRoot 'node-extracted'
        Expand-Archive -LiteralPath $archive -DestinationPath $unpackRoot -Force
        $extracted = Join-Path $unpackRoot ([IO.Path]::GetFileNameWithoutExtension($match.Groups[2].Value))
        $nodeTarget = Join-Path $toolsRoot 'node'
        New-Item -ItemType Directory -Force -Path $nodeTarget | Out-Null
        Copy-Item -Path (Join-Path $extracted '*') -Destination $nodeTarget -Recurse -Force
        $nodePath = Find-StudioNode
        if (-not $nodePath) { throw 'Node.js hazirlandi ancak calistirilamadi.' }
    } else { Write-Host '[2/4] Uyumlu Node.js bulundu.' }
    $env:PATH = (Split-Path $nodePath) + ';' + $env:PATH
    Write-Host '[3/4] Paketler ve arayuz hazirlaniyor...'
    $launcherArgs = @((Join-Path $studioRoot 'launcher.py'),'--setup-only')
    if (-not $SkipModels) { $launcherArgs += '--download-models' }
    & $pythonPath @launcherArgs
    if ($LASTEXITCODE -ne 0) { throw 'Uygulama kurulumu tamamlanamadi. logs\setup.log dosyasini kontrol edin.' }
    Write-Host '[4/4] Kurulum tamamlandi!' -ForegroundColor Green
    Write-Host 'Ac: calistir.bat / CALISTIR.bat | Kapat: stop.bat'
    Stop-Transcript | Out-Null
    if (-not $NoPause) { Read-Host 'Pencereyi kapatmak icin Enter' | Out-Null }
    exit 0
} catch {
    Write-Host ("HATA: " + $_.Exception.Message) -ForegroundColor Red
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
    if (-not $NoPause) { Read-Host 'Pencereyi kapatmak icin Enter' | Out-Null }
    exit 1
}
