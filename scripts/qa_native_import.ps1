param(
    [ValidateSet('Inspect','Capture','Click','Select','File','Restore','Close','Input','Key','Resize')][string]$Action = 'Inspect',
    [string]$Name = '', [string]$Value = '', [string]$OutputPath = '', [int]$Index = 0
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class PetroLabCapture {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr w, string text);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
}
'@
$root = [System.Windows.Automation.AutomationElement]::RootElement
$condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, 'Tauri Window')
$window = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $condition)
if (-not $window) { throw 'No Tauri window found' }
if ($Action -eq 'Close') {
    $window.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern).Close()
    return
}
if ($Action -eq 'Restore') {
    $window.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern).SetWindowVisualState([System.Windows.Automation.WindowVisualState]::Normal)
    return
}
if ($Action -eq 'Resize') {
    if ($Value -notmatch '^(\d+)x(\d+)$') { throw 'Use widthxheight' }
    $window.GetCurrentPattern([System.Windows.Automation.TransformPattern]::Pattern).Resize([double]$Matches[1], [double]$Matches[2])
    return
}
if ($Action -eq 'Capture') {
    $rect = New-Object PetroLabCapture+RECT
    $handle = [IntPtr]$window.Current.NativeWindowHandle
    [void][PetroLabCapture]::GetWindowRect($handle, [ref]$rect)
    $bitmap = New-Object System.Drawing.Bitmap(($rect.Right-$rect.Left), ($rect.Bottom-$rect.Top))
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $dc = $graphics.GetHdc()
    try { $ok = [PetroLabCapture]::PrintWindow($handle, $dc, 2) } finally { $graphics.ReleaseHdc($dc) }
    if (-not $ok) { throw 'PrintWindow failed' }
    try { $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png) }
    finally { $graphics.Dispose(); $bitmap.Dispose() }
    Write-Output $OutputPath
    return
}
if ($Action -eq 'File') {
    $dialogCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, '#32770')
    $dialog = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $dialogCondition) | Where-Object { $_.Current.ProcessId -eq $window.Current.ProcessId } | Select-Object -First 1
    if (-not $dialog) { throw 'No native file picker found' }
    $dialogElements = $dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $edits = $dialogElements | Where-Object { $_.Current.ClassName -eq 'Edit' }
    $edit = $edits | Where-Object { $_.Current.AutomationId -eq '1148' } | Select-Object -First 1
    if (-not $edit) { $edits | ForEach-Object { $_.Current | Select-Object Name,AutomationId }; throw 'File-name edit not found' }
    [void][PetroLabCapture]::SendMessage([IntPtr]$edit.Current.NativeWindowHandle, 0x000C, [IntPtr]::Zero, $Value)
    $open = $dialogElements | Where-Object { $_.Current.AutomationId -eq '1' -and $_.Current.ClassName -eq 'Button' } | Select-Object -First 1
    [void][PetroLabCapture]::PostMessage([IntPtr]$open.Current.NativeWindowHandle, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero)
    return
}
$elements = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
if ($Action -eq 'Inspect') {
    $elements | ForEach-Object { $entry=$_.Current; if ($entry.Name) { [PSCustomObject]@{ Name=$entry.Name; Type=$entry.ControlType.ProgrammaticName; Enabled=$entry.IsEnabled; Offscreen=$entry.IsOffscreen; Handle=$entry.NativeWindowHandle } } } | ConvertTo-Json -Depth 3
    return
}
$matches = @($elements | Where-Object { $_.Current.Name.Trim() -eq $Name.Trim() -and $_.Current.IsEnabled })
$pattern = if ($Action -eq 'Click') { [System.Windows.Automation.InvokePattern]::Pattern } elseif ($Action -eq 'Input') { [System.Windows.Automation.ValuePattern]::Pattern } else { $null }
if ($pattern) { $matches = @($matches | Where-Object { (@($_.GetSupportedPatterns().Id) -contains $pattern.Id) -or ($Action -eq 'Click' -and @($_.GetSupportedPatterns().Id) -contains [System.Windows.Automation.TogglePattern]::Pattern.Id) }) }
if ($matches.Length -le $Index) { throw "Element not found: $Name" }
$element = $matches[$Index]
if ($Action -eq 'Click') {
    if (@($element.GetSupportedPatterns().Id) -contains [System.Windows.Automation.InvokePattern]::Pattern.Id) {
        $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    } else { $element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Toggle() }
} elseif ($Action -eq 'Select') {
    $element.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
    $option = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $Value)))
    if (-not $option) { throw "Option not found: $Value" }
    $option.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
} elseif ($Action -eq 'Input') {
    $element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($Value)
} elseif ($Action -eq 'Key') {
    Add-Type -AssemblyName System.Windows.Forms
    $element.SetFocus()
    [System.Windows.Forms.SendKeys]::SendWait($Value)
}
