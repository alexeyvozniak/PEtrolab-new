param(
    [string]$BundleRoot = "desktop/src-tauri/target/release/bundle",
    [Parameter(Mandatory = $true)]
    [string]$ImportSource,
    [string]$QaOutput = (Join-Path $env:RUNNER_TEMP "petrolab-ui-smoke")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Get-UiElement {
    param(
        [Parameter(Mandatory = $true)] [System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory = $true)] [string]$Name,
        [int]$TimeoutSeconds = 20
    )

    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        $Name
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $element = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
        if ($null -ne $element) {
            return $element
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw "UI element '$Name' did not appear within $TimeoutSeconds seconds."
}

function Invoke-UiElement {
    param(
        [Parameter(Mandatory = $true)] [System.Windows.Automation.AutomationElement]$Element,
        [Parameter(Mandatory = $true)] [string]$Description
    )

    try {
        $pattern = $Element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $pattern.Invoke()
    } catch {
        throw "Could not invoke '$Description': $($_.Exception.Message)"
    }
}

function Get-OpenFileDialog {
    param([int]$TimeoutSeconds = 12)

    $windowCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Window
    )
    $editCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Edit
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $windows = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
            [System.Windows.Automation.TreeScope]::Children,
            $windowCondition
        )
        foreach ($window in $windows) {
            $edits = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCondition)
            foreach ($edit in $edits) {
                if ($edit.Current.Name -eq "File name:") {
                    return @{ Window = $window; FileName = $edit }
                }
            }
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw "The Windows file chooser did not expose its 'File name:' field."
}

function Set-FileDialogPath {
    param(
        [Parameter(Mandatory = $true)] $Dialog,
        [Parameter(Mandatory = $true)] [string]$Path
    )

    try {
        $value = $Dialog.FileName.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $value.SetValue($Path)
    } catch {
        throw "Could not set the selected file path in the Windows chooser: $($_.Exception.Message)"
    }

    $buttonCondition = New-Object System.Windows.Automation.AndCondition @(
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Button
        )),
        (New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty,
            "Open"
        ))
    )
    $open = $Dialog.Window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $buttonCondition)
    if ($null -eq $open) {
        throw "The Windows file chooser did not expose its 'Open' button."
    }
    Invoke-UiElement -Element $open -Description "Open selected import source"
}

function Save-DesktopScreenshot {
    param([Parameter(Mandatory = $true)] [string]$Path)

    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

$bundle = Resolve-Path $BundleRoot
$importSource = (Resolve-Path $ImportSource).Path
$sourceHashBefore = (Get-FileHash -Algorithm SHA256 -LiteralPath $importSource).Hash
New-Item -ItemType Directory -Force -Path $QaOutput | Out-Null
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

    $appWindow = [System.Windows.Automation.AutomationElement]::FromHandle($appProcess.MainWindowHandle)
    $chooseFile = Get-UiElement -Root $appWindow -Name "Выбрать файл"
    Invoke-UiElement -Element $chooseFile -Description "Выбрать файл"
    $dialog = Get-OpenFileDialog
    Set-FileDialogPath -Dialog $dialog -Path $importSource

    $importButton = Get-UiElement -Root $appWindow -Name "Импортировать таблицу" -TimeoutSeconds 35
    Save-DesktopScreenshot -Path (Join-Path $QaOutput "01-clean-table-ready.png")
    Invoke-UiElement -Element $importButton -Description "Импортировать таблицу"

    $importedAnalysis = Get-UiElement -Root $appWindow -Name "UI-1" -TimeoutSeconds 35
    if ($null -eq $importedAnalysis) {
        throw "The imported Analysis UI-1 did not appear in the installed PetroLab table."
    }
    Save-DesktopScreenshot -Path (Join-Path $QaOutput "02-imported-analyses.png")

    $sourceHashAfter = (Get-FileHash -Algorithm SHA256 -LiteralPath $importSource).Hash
    if ($sourceHashBefore -ne $sourceHashAfter) {
        throw "PetroLab changed the original import source. Before: $sourceHashBefore; after: $sourceHashAfter"
    }

    Write-Host "Installed PetroLab UI smoke test passed: window, file chooser, Clean Table import, analyses table and immutable source are verified."
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
