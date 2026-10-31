param([switch]$FunctionsOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-PlainPath([string]$Path) {
    $part = [IO.Path]::GetFullPath($Path)
    while ($part) {
        if (Test-Path -LiteralPath $part) {
            $item = Get-Item -LiteralPath $part -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "A linked path is not permitted: $part. Use a plain course folder."
            }
        }
        $parent = [IO.Path]::GetDirectoryName($part)
        if ($parent -eq $part) { break }
        $part = $parent
    }
}

function Get-PythonInfo([string]$Python) {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
    $probe = "import json,sys,platform,struct,sysconfig; print(json.dumps(dict(implementation=platform.python_implementation(),version=platform.python_version(),bits=struct.calcsize('P')*8,gil=not bool(sysconfig.get_config_var('Py_GIL_DISABLED')),conda='conda' in sys.version.lower() or __import__('os').path.isdir(__import__('os').path.join(sys.base_prefix,'conda-meta')))))"
    $result = & $Python -I -c $probe
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect Python: $Python. Repair this installation first." }
    try { $info = $result | ConvertFrom-Json } catch { throw "Cannot read Python details: $Python. Repair this installation first." }
    if ($info.implementation -ne 'CPython' -or $info.version -notmatch '^3\.13\.\d+$' -or $info.bits -ne 64 -or -not $info.gil -or $info.conda) {
        throw "Use standard CPython x64 3.13.x with the GIL: $Python. Repair or remove this incompatible installation first."
    }
    return $info
}

function Get-PythonCandidates {
    foreach ($hive in @('HKCU:', 'HKLM:')) {
        foreach ($base in @('Software\Python\PythonCore', 'Software\Wow6432Node\Python\PythonCore')) {
            $key = "$hive\$base"
            if (Test-Path $key) {
                foreach ($entry in Get-ChildItem $key) {
                    if ($entry.PSChildName -like '3.13*') {
                        $installKey = Join-Path $entry.PSPath 'InstallPath'
                        if (-not (Test-Path $installKey)) { throw "Python 3.13 has an incomplete registry entry: $($entry.Name). Repair or remove it first." }
                        $item = Get-Item $installKey
                        $exe = $item.GetValue('ExecutablePath')
                        if (-not $exe) {
                            $folder = $item.GetValue('')
                            if (-not $folder) { throw "Python 3.13 has no installation path: $($entry.Name). Repair or remove it first." }
                            $exe = Join-Path $folder 'python.exe'
                        }
                        [pscustomobject]@{ Path = $exe; Registered = $true }
                    }
                }
            }
        }
    }
    foreach ($folder in @("$env:LOCALAPPDATA\Programs\Python\Python313", "$env:ProgramFiles\Python313", "${env:ProgramFiles(x86)}\Python313", 'C:\Python313')) {
        $exe = Join-Path $folder 'python.exe'
        if (Test-Path -LiteralPath $exe) { [pscustomobject]@{ Path = $exe; Registered = $true } }
    }
    foreach ($command in @(Get-Command python.exe, python3.exe -All -ErrorAction SilentlyContinue)) {
        if ($command.Source -and $command.Source -notmatch '\\Microsoft\\WindowsApps\\') {
            [pscustomobject]@{ Path = $command.Source; Registered = $false }
        }
    }
}

function Select-CoursePython($Candidates) {
    $selected = $null
    foreach ($candidate in $Candidates) {
        try {
            $null = Get-PythonInfo $candidate.Path
            if (-not $selected) { $selected = $candidate.Path }
        } catch {
            if ($candidate.Registered) { throw }
        }
    }
    return $selected
}

function Assert-NoRelatedPython {
    foreach ($hive in @('HKCU:', 'HKLM:')) {
        foreach ($base in @('Software\Microsoft\Windows\CurrentVersion\Uninstall', 'Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
            $key = "$hive\$base"
            if (Test-Path $key) {
                foreach ($entry in Get-ChildItem $key) {
                    $name = $entry.GetValue('DisplayName')
                    if ($name -match '(?i)Python\s+3\.13') {
                        throw "An installed Python 3.13 entry exists: $name. Repair or remove it before setup."
                    }
                }
            }
        }
    }
}

function Assert-Installer([string]$Path) {
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne 'edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403') {
        throw 'Python installer SHA-256 differs. Keep the file and inspect the setup log.'
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch '(?:^|,\s*)O=Python Software Foundation(?:,|$)') {
        throw 'Python installer signature differs. A valid Python Software Foundation signature is required.'
    }
}

function Get-InstallerArguments([string]$Target, [string]$Log) {
    return @('/quiet', '/norestart', '/log', "`"$Log`"", "TargetDir=`"$Target`"", 'InstallAllUsers=0', 'Include_pip=1', 'Include_test=0', 'Include_launcher=0', 'InstallLauncherAllUsers=0', 'PrependPath=0', 'AppendPath=0', 'AssociateFiles=0', 'Shortcuts=0', 'Include_doc=0')
}

function Invoke-CourseStep([string]$Python, [string[]]$Arguments) {
    & $Python -E @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Course command failed with exit code $LASTEXITCODE. Read the setup log. Command: $Python $Arguments" }
}

function Set-CoursePipEnvironment {
    # Change this process only. Do not change the user's saved settings.
    foreach ($entry in @(Get-ChildItem Env:)) {
        if ($entry.Name -like 'PIP_*' -or $entry.Name -like 'PYTHON*') {
            Remove-Item -LiteralPath (Join-Path 'Env:' $entry.Name)
        }
    }
    # pip documents os.devnull as the switch that disables all config files.
    $env:PIP_CONFIG_FILE = 'nul'
    $env:PIP_REQUIRE_VIRTUALENV = 'true'
}

function Get-CourseVenv([string]$Root, [string]$Python) {
    $venv = Join-Path $Root '.venv'
    Assert-PlainPath $venv
    $exe = Join-Path $venv 'Scripts\python.exe'
    Assert-PlainPath $exe
    Assert-PlainPath (Join-Path $venv 'pyvenv.cfg')
    if (Test-Path -LiteralPath $venv) {
        if (-not (Test-Path -LiteralPath (Join-Path $venv 'pyvenv.cfg') -PathType Leaf)) { throw "The course .venv is incomplete. Keep it and use a fresh course folder: $venv" }
        $config = Get-Content -LiteralPath (Join-Path $venv 'pyvenv.cfg') -Raw
        if ($config -match '(?im)^\s*include-system-site-packages\s*=\s*true\s*$') { throw "The course .venv uses system packages. Keep it and use a fresh course folder: $venv" }
        $null = Get-PythonInfo $exe
        $probe = & $exe -I -c 'import sys; print(sys.prefix != sys.base_prefix)'
        if ($LASTEXITCODE -ne 0 -or $probe -ne 'True') { throw "The course .venv is invalid. Keep it and use a fresh course folder: $venv" }
    } else {
        Invoke-CourseStep $Python @('-m', 'venv', $venv)
        Assert-PlainPath $venv
        $null = Get-PythonInfo $exe
    }
    return $exe
}

function Start-CourseSetup {
    $root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
    Assert-PlainPath $root
    if ($root.Length -gt 80 -or $root -match '(?i)(^|\\)OneDrive[^\\]*(\\|$)') { throw 'Move the course to a folder outside OneDrive with a path of 80 characters or less.' }
    foreach ($oneDrivePath in @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial)) {
        if ($oneDrivePath -and ($root -eq $oneDrivePath -or $root.StartsWith($oneDrivePath.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase))) { throw 'Move the course outside OneDrive.' }
    }
    if (-not [Environment]::Is64BitOperatingSystem -or $env:OS -ne 'Windows_NT' -or ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64')) { throw 'Use standard Windows x64.' }
    Assert-PlainPath (Join-Path $root '.venv')
    $outputBase = Join-Path $root 'outputs'
    Assert-PlainPath $outputBase
    $output = Join-Path $outputBase ('setup_' + (Get-Date -Format 'yyyyMMddTHHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8))
    Assert-PlainPath $output
    $null = New-Item -ItemType Directory -Path $output
    $log = Join-Path $output 'setup.log'
    Start-Transcript -LiteralPath $log | Out-Null
    try {
        Write-Host "Setup log: $log"
        $existingVenv = $null
        if (Test-Path -LiteralPath (Join-Path $root '.venv')) { $existingVenv = Get-CourseVenv $root $null }
        Write-Host 'Check Python 3.13.'
        $python = Select-CoursePython @(Get-PythonCandidates)
        if (-not $python -and $existingVenv) { $python = $existingVenv }
        if (-not $python) {
            Assert-NoRelatedPython
            $target = Join-Path $env:LOCALAPPDATA ('Programs\Python\HECRASCourse31315_' + [guid]::NewGuid().ToString('N').Substring(0,8))
            Assert-PlainPath $target
            if (Test-Path -LiteralPath $target) { throw "The Python target already exists: $target" }
            $installer = Join-Path $output 'python-3.13.15-amd64.exe'
            Write-Host 'Download Python 3.13.15 from python.org.'
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe' -OutFile $installer
            Assert-Installer $installer
            $arguments = Get-InstallerArguments $target (Join-Path $output 'python-install.log')
            $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
            if ($process.ExitCode -ne 0) { throw "Python installation failed with exit code $($process.ExitCode). Read python-install.log." }
            $python = Join-Path $target 'python.exe'
            if ((Get-PythonInfo $python).version -ne '3.13.15') { throw 'The installed Python version differs from 3.13.15.' }
        }
        Write-Host "Use Python: $python"
        $venvPython = Get-CourseVenv $root $python
        Write-Host 'Install the pinned course packages.'
        Set-CoursePipEnvironment
        Invoke-CourseStep $venvPython @('-m', 'pip', 'install', '--only-binary=:all:', '-r', (Join-Path $root 'requirements-dev.txt'), '-c', (Join-Path $root 'requirements-windows-py313.txt'))
        Invoke-CourseStep $venvPython @((Join-Path $root 'scripts\check_environment.py'))
        Write-Host 'Prepare the course model inputs.'
        Invoke-CourseStep $venvPython @((Join-Path $root 'scripts\course_setup.py'), 'prepare')
        Write-Host 'SETUP COMPLETE. Next, open Run Models.cmd.'
    } catch {
        Write-Host "SETUP FAILED: $($_.Exception.Message)"
        Write-Host "Read the setup log: $log"
        throw
    } finally { Stop-Transcript | Out-Null }
}

if (-not $FunctionsOnly) {
    try { Start-CourseSetup; exit 0 } catch { Write-Host "SETUP FAILED: $($_.Exception.Message)"; exit 1 }
}
