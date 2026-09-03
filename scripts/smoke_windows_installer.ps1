param(
    [string]$BundleRoot = "desktop/src-tauri/target/release/bundle"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

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
$installed = $false

try {
    Write-Host "Installing $($msi.FullName)"
    $installer = Start-Process -FilePath "msiexec.exe" -ArgumentList $installArgs -Wait -PassThru
    if ($installer.ExitCode -notin @(0, 3010)) {
        if (Test-Path $installerLog) {
            Get-Content $installerLog -Tail 120 | Write-Host
        }
        throw "MSI installation failed with exit code $($installer.ExitCode)."
    }
    $installed = $true

    $candidateRoots = @(
        $installRoot,
        (Join-Path $env:LOCALAPPDATA "PetroLab"),
        (Join-Path $env:LOCALAPPDATA "Programs\PetroLab"),
        (Join-Path $env:ProgramFiles "PetroLab")
    )
    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    if ($programFilesX86) {
        $candidateRoots += Join-Path $programFilesX86 "PetroLab"
    }

    $appExecutable = $null
    foreach ($candidateRoot in $candidateRoots | Select-Object -Unique) {
        if (-not (Test-Path $candidateRoot)) {
            continue
        }
        $appExecutable = Get-ChildItem -Path $candidateRoot -Recurse -File -Filter "*.exe" |
            Where-Object {
                $_.Name -match "petrolab" -and
                $_.Name -notmatch "service|unins|uninstall"
            } |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if ($null -ne $appExecutable) {
            break
        }
    }

    if ($null -eq $appExecutable) {
        throw "Installed PetroLab executable was not found. MSI log: $installerLog"
    }

    $databaseCandidates = @(
        (Join-Path $env:APPDATA "org.petrolab.desktop\petrolab-v2.sqlite"),
        (Join-Path $env:LOCALAPPDATA "org.petrolab.desktop\petrolab-v2.sqlite")
    )
    foreach ($database in $databaseCandidates) {
        if (Test-Path $database) {
            Remove-Item -LiteralPath $database -Force
        }
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

        $serviceProcesses = @(Get-Process -Name "petrolab-service" -ErrorAction SilentlyContinue)
        if ($serviceProcesses.Count -gt 0) {
            $serviceReady = $true
        }

        foreach ($database in $databaseCandidates) {
            if (Test-Path $database) {
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

    Write-Host "Installed PetroLab smoke test passed: window, scientific service and project database are ready."
}
finally {
    if ($null -ne $appProcess -and -not $appProcess.HasExited) {
        Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
        $appProcess.WaitForExit(5000) | Out-Null
    }
    foreach ($serviceProcess in $serviceProcesses) {
        Stop-Process -Id $serviceProcess.Id -Force -ErrorAction SilentlyContinue
    }

    if ($installed) {
        $uninstallArgs = @("/x", ('"{0}"' -f $msi.FullName), "/qn", "/norestart")
        $uninstaller = Start-Process -FilePath "msiexec.exe" -ArgumentList $uninstallArgs -Wait -PassThru
        if ($uninstaller.ExitCode -notin @(0, 1605, 3010)) {
            Write-Warning "MSI uninstall returned $($uninstaller.ExitCode)."
        }
    }
}
