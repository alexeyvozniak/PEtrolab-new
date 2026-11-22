param(
    [string]$BundleRoot = "desktop/src-tauri/target/release/bundle",
    [string]$BaselineMsi,
    [string]$HistoricalSource,
    [string]$UiEvidence
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# This test installs and uninstalls a product; never run it on a user's machine.
if ($env:GITHUB_ACTIONS -ne "true" -or $env:RUNNER_ENVIRONMENT -ne "github-hosted" -or -not $env:RUNNER_TEMP) {
    throw "Installer smoke test requires an isolated CI runner with RUNNER_TEMP."
}
$databaseCandidates = @(
    (Join-Path ([Environment]::GetFolderPath("ApplicationData")) "org.petrolab.desktop\petrolab-v2.sqlite"),
    (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "org.petrolab.desktop\petrolab-v2.sqlite")
)
foreach ($database in $databaseCandidates) {
    if (Test-Path -LiteralPath $database) {
        throw "Existing PetroLab database detected; refusing to install or modify it: $database"
    }
}

$bundle = Resolve-Path $BundleRoot
$msi = Get-ChildItem -Path $bundle -Recurse -File -Filter "*.msi" |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1

if ($null -eq $msi) {
    throw "PetroLab MSI was not found under $bundle"
}

$runId = [guid]::NewGuid().ToString()
$installRoot = Join-Path $env:RUNNER_TEMP "PetroLab-installed-$runId"
$installerLog = Join-Path $env:RUNNER_TEMP "PetroLab-install-$runId.log"
$installArgs = @(
    "/i",
    ('"{0}"' -f $msi.FullName),
    "/qn",
    "/norestart",
    ('INSTALLDIR="{0}"' -f $installRoot),
    "/l*v",
    ('"{0}"' -f $installerLog)
)

$appProcess = $null
$serviceProcesses = @()
$installedService = $null
$installed = $false
$previousInstalled = $false
$baselinePath = if ($BaselineMsi) { (Resolve-Path -LiteralPath $BaselineMsi).Path } else { $null }
$database = $null
$upgradeState = Join-Path $env:RUNNER_TEMP "PetroLab-project-$runId.json"
$env:PETROLAB_PROJECT_DATABASE = $null
$env:PETROLAB_PYTHON = $null

function Get-InstalledServiceProcesses {
    if ($installedService) {
        Get-CimInstance Win32_Process -Filter "Name = 'petrolab-service.exe'" |
            Where-Object { $_.ExecutablePath -eq $installedService } |
            ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
    }
}

try {
    if ($baselinePath) {
        $previousArgs = @(
            "/i", ('"{0}"' -f $baselinePath), "/qn", "/norestart",
            ('INSTALLDIR="{0}"' -f $installRoot), "/l*v",
            ('"{0}"' -f (Join-Path $env:RUNNER_TEMP "PetroLab-baseline-$runId.log"))
        )
        $previousInstaller = Start-Process -FilePath "msiexec.exe" -WindowStyle Hidden -ArgumentList $previousArgs -Wait -PassThru
        if ($previousInstaller.ExitCode -ne 0) { throw "Baseline MSI installation returned $($previousInstaller.ExitCode)." }
        $previousInstalled = $true
        $database = $databaseCandidates[0]
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $database) | Out-Null
        $baselineService = Join-Path $installRoot "binaries\petrolab-service.exe"
        & python (Join-Path $PSScriptRoot "qa_installer_project.py") seed $baselineService $database $upgradeState
        if ($LASTEXITCODE -ne 0) { throw "Failed to seed the baseline project." }
        $previousProduct = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
            Where-Object { $_.PSObject.Properties['DisplayName'] -and $_.DisplayName -eq 'PetroLab' } |
            Select-Object -ExpandProperty PSPath
        if (@($previousProduct).Count -ne 1) { throw "Could not identify the baseline MSI registration." }
    }
    Write-Host "Installing $($msi.FullName)"
    $installer = Start-Process -FilePath "msiexec.exe" -WindowStyle Hidden -ArgumentList $installArgs -Wait -PassThru
    if ($installer.ExitCode -ne 0) {
        if (Test-Path $installerLog) {
            Get-Content $installerLog -Tail 120 | Write-Host
        }
        throw "MSI installation failed with exit code $($installer.ExitCode)."
    }
    $installed = $true
    if ($baselinePath) {
        if (Test-Path -LiteralPath $previousProduct) { throw "The candidate did not replace the baseline MSI registration." }
        $previousInstalled = $false
    }

    $appExecutable = Get-ChildItem -LiteralPath $installRoot -Recurse -File -Filter "*.exe" |
            Where-Object {
                $_.Name -match "petrolab" -and
                $_.Name -notmatch "service|unins|uninstall"
            } |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1

    if ($null -eq $appExecutable) {
        throw "Installed PetroLab executable was not found. MSI log: $installerLog"
    }

    $installedService = Join-Path $appExecutable.DirectoryName "binaries\petrolab-service.exe"
    & python (Join-Path $PSScriptRoot "qa_packaged_import.py") --executable $installedService
    if ($LASTEXITCODE -ne 0) {
        throw "Installed service failed the isolated import and restart check."
    }
    if ($baselinePath) {
        & python (Join-Path $PSScriptRoot "qa_installer_project.py") verify $installedService $database $upgradeState
        if ($LASTEXITCODE -ne 0) { throw "The upgrade changed or lost the baseline project." }
    }

    if ($HistoricalSource) {
        & python (Join-Path $PSScriptRoot "qa_installer_project.py") historical $installedService $HistoricalSource
        if ($LASTEXITCODE -ne 0) { throw "The installed candidate did not safely migrate the historical project." }
    }

    Write-Host "Launching $($appExecutable.FullName)"
    $appProcess = Start-Process -FilePath $appExecutable.FullName -PassThru
    $windowReady = $false
    $serviceReady = $false
    $databaseReady = $false

    for ($attempt = 0; $attempt -lt 40; $attempt += 1) {
        Start-Sleep -Milliseconds 500
        $appProcess.Refresh()
        if ($appProcess.HasExited) {
            throw "Installed PetroLab exited during startup with code $($appProcess.ExitCode)."
        }

        if ($appProcess.MainWindowHandle -ne 0) {
            $windowReady = $true
        }

        # Only count the service belonging to this app, never another open project.
        $serviceProcesses = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($appProcess.Id)" |
            Where-Object { $_.Name -eq "petrolab-service.exe" } |
            ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
        if ($serviceProcesses.Count -gt 0) {
            $serviceReady = $true
        }

        foreach ($candidate in $databaseCandidates) {
            if (Test-Path -LiteralPath $candidate) {
                $database = $candidate
                $databaseReady = $true
                break
            }
        }

        if ($windowReady -and $serviceReady -and $databaseReady) {
            break
        }
    }

    if (-not $windowReady) {
        throw "PetroLab process stayed alive but no main window appeared."
    }
    if (-not $serviceReady) {
        throw "PetroLab window opened but the packaged scientific service did not start."
    }
    if (-not $databaseReady) {
        throw "PetroLab opened but did not create its fresh project SQLite database."
    }

    Write-Host "PetroLab window, scientific service and project database are ready."
    if (-not $appProcess.CloseMainWindow() -or -not $appProcess.WaitForExit(15000)) {
        throw "Installed PetroLab did not exit after closing its main window."
    }

    # The bundled PyInstaller loader and its worker are separate processes.
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while (@(Get-InstalledServiceProcesses).Count -gt 0) {
        if ([DateTime]::UtcNow -ge $deadline) {
            throw "Installed scientific service stayed active after closing PetroLab."
        }
        Start-Sleep -Milliseconds 250
    }

    if ($UiEvidence) {
        & node (Join-Path $PSScriptRoot "qa_installer_ui.mjs") $appExecutable.FullName $UiEvidence
        if ($LASTEXITCODE -ne 0) { throw "Installed PetroLab failed the AT-14 native workflow." }
    }

    $beforeUninstall = (Get-FileHash -Algorithm SHA256 -LiteralPath $database).Hash
}
finally {
    if ($null -ne $appProcess -and -not $appProcess.HasExited) {
        Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
        $appProcess.WaitForExit(5000) | Out-Null
    }
    foreach ($serviceProcess in @(Get-InstalledServiceProcesses)) {
        Stop-Process -Id $serviceProcess.Id -Force -ErrorAction SilentlyContinue
        $serviceProcess.WaitForExit(5000) | Out-Null
    }

    if ($installed) {
        $uninstallArgs = @("/x", ('"{0}"' -f $msi.FullName), "/qn", "/norestart")
        $uninstaller = Start-Process -FilePath "msiexec.exe" -WindowStyle Hidden -ArgumentList $uninstallArgs -Wait -PassThru
        $uninstallStatus = $uninstaller.ExitCode
    }
    if ($previousInstalled) {
        Start-Process -FilePath "msiexec.exe" -WindowStyle Hidden -Wait -ArgumentList @("/x", ('"{0}"' -f $baselinePath), "/qn", "/norestart")
    }
}

if ($uninstallStatus -ne 0 -or (Test-Path -LiteralPath $appExecutable.FullName) -or (Test-Path -LiteralPath $installedService)) {
    throw "Uninstall left application components or returned $uninstallStatus."
}
if (-not $database -or -not (Test-Path -LiteralPath $database)) {
    throw "Uninstall removed persistent project data."
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $database).Hash -ne $beforeUninstall) {
    throw "Uninstall changed the persistent project database."
}
Write-Host "Installed PetroLab smoke test passed: startup, shutdown and uninstall preserved the project."
