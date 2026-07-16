[CmdletBinding()]
param(
    [ValidateSet('setup', 'check', 'build', 'play', 'editor', 'unpack')]
    [string]$Action = 'check',
    [string]$Mod = 'local-dev',
    [switch]$Vanilla,
    [switch]$Windowed,
    [switch]$Borderless,
    [switch]$Wait,
    [int]$XRes = 0,
    [int]$YRes = 0,
    [string]$Map = ''
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$LocalRoot = Join-Path $RepoRoot '.local'
$StatePath = Join-Path $LocalRoot 'state.json'
$ReleaseApi = 'https://api.github.com/repos/TheSuperHackers/GeneralsGameCode/releases/latest'

function Find-ZeroHour {
    $uninstallRoots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    $product = Get-ItemProperty $uninstallRoots -ErrorAction SilentlyContinue |
        Where-Object {
            $_.InstallLocation -and
            $_.DisplayName -match 'Command.*Conquer.*Generals.*Zero Hour'
        } |
        Select-Object -First 1
    if (-not $product -or -not $product.InstallLocation) {
        throw 'Could not find an installed EA/Steam copy of Command & Conquer Generals and Zero Hour.'
    }

    $gameDir = Join-Path $product.InstallLocation 'Command and Conquer Generals Zero Hour'
    foreach ($required in @('Generals.exe', 'WorldBuilder.exe', 'INIZH.big', 'MapsZH.big')) {
        if (-not (Test-Path (Join-Path $gameDir $required))) {
            throw "Retail Zero Hour is missing $required under $gameDir"
        }
    }
    return $gameDir
}

function Install-Runtime {
    $gameDir = Find-ZeroHour
    New-Item -ItemType Directory -Force -Path $LocalRoot | Out-Null
    $headers = @{ 'User-Agent' = 'CommandConquer-local-dev'; 'Accept' = 'application/vnd.github+json' }
    $release = Invoke-RestMethod -Headers $headers -Uri $ReleaseApi
    $asset = $release.assets | Where-Object { $_.name -like 'generalszh-*.zip' } | Select-Object -First 1
    if (-not $asset) {
        throw "Release $($release.tag_name) does not contain a generalszh ZIP asset."
    }

    $downloadDir = Join-Path $LocalRoot 'downloads'
    $runtimeDir = Join-Path $LocalRoot (Join-Path 'runtime' $release.tag_name)
    $zipPath = Join-Path $downloadDir $asset.name
    New-Item -ItemType Directory -Force -Path $downloadDir, $runtimeDir | Out-Null
    if (-not (Test-Path $zipPath) -or (Get-Item $zipPath).Length -ne $asset.size) {
        Write-Host "Downloading maintained Zero Hour runtime $($release.tag_name)..."
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath
    }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $runtimeDir -Force

    foreach ($required in @('generalszh.exe')) {
        if (-not (Test-Path (Join-Path $runtimeDir $required))) {
            throw "Runtime archive is missing $required"
        }
    }

    $state = [ordered]@{
        gameDir = $gameDir
        release = $release.tag_name
        releaseUrl = $release.html_url
        runtimeDir = $runtimeDir
        archiveSha256 = (Get-FileHash $zipPath -Algorithm SHA256).Hash
        configuredAt = (Get-Date).ToString('o')
    }
    $state | ConvertTo-Json | Set-Content -Encoding UTF8 $StatePath
    Write-Host "Runtime ready: $runtimeDir"
    return [pscustomobject]$state
}

function Get-State {
    if (-not (Test-Path $StatePath)) {
        return Install-Runtime
    }
    $state = Get-Content -Raw $StatePath | ConvertFrom-Json
    if (-not (Test-Path $state.gameDir) -or -not (Test-Path (Join-Path $state.runtimeDir 'generalszh.exe'))) {
        return Install-Runtime
    }
    return $state
}

function Build-Mod([object]$state) {
    $manifest = Join-Path $RepoRoot (Join-Path 'mods' (Join-Path $Mod 'mod.json'))
    if (-not (Test-Path $manifest)) {
        throw "Unknown mod '$Mod': expected $manifest"
    }
    $outputDir = Join-Path $LocalRoot 'mods'
    $output = Join-Path $outputDir "$Mod.big"
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    $buildOutput = & python (Join-Path $PSScriptRoot 'build_mod.py') $manifest $state.gameDir $output
    if ($LASTEXITCODE -ne 0) { throw "Mod build failed with exit code $LASTEXITCODE" }
    Write-Host $buildOutput
    return $output
}

function Get-WidescreenResolution {
    if (($XRes -gt 0) -xor ($YRes -gt 0)) {
        throw 'Specify both -XRes and -YRes, or leave both at 0 for automatic widescreen detection.'
    }
    if ($XRes -gt 0 -and $YRes -gt 0) {
        return [pscustomobject]@{ Width = $XRes; Height = $YRes; Device = 'manual override' }
    }

    try {
        Add-Type -AssemblyName System.Windows.Forms
        $screen = [System.Windows.Forms.Screen]::AllScreens |
            Where-Object { $_.Bounds.Width -ge (1.5 * $_.Bounds.Height) } |
            Sort-Object @{ Expression = { $_.Bounds.Width * $_.Bounds.Height }; Descending = $true }, `
                        @{ Expression = { $_.Primary }; Descending = $true } |
            Select-Object -First 1
        if ($screen) {
            return [pscustomobject]@{
                Width = $screen.Bounds.Width
                Height = $screen.Bounds.Height
                Device = $screen.DeviceName
            }
        }
    } catch {
        Write-Verbose "Display detection failed: $($_.Exception.Message)"
    }
    return [pscustomobject]@{ Width = 1920; Height = 1080; Device = '1080p fallback' }
}

function Get-UserMapsDirectory {
    $documents = [Environment]::GetFolderPath('MyDocuments')
    if (-not $documents) { throw 'Windows did not report a Documents directory.' }
    return Join-Path $documents 'Command and Conquer Generals Zero Hour Data\Maps'
}

function Sync-WindowedCursorAssets([object]$state) {
    $source = Join-Path $state.gameDir 'Data\Cursors'
    $target = Join-Path $state.runtimeDir 'Data\Cursors'
    if (-not (Test-Path $source)) { throw "Retail cursor assets are missing: $source" }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Path (Join-Path $source '*.ani') -Destination $target -Force
    if ((Get-ChildItem -LiteralPath $target -File -Filter '*.ani').Count -lt 1) {
        throw "No windowed cursor assets were copied to $target"
    }
}

function Apply-RuntimePatches([object]$state) {
    $executable = Join-Path $state.runtimeDir 'generalszh.exe'
    $patchOutput = & python (Join-Path $PSScriptRoot 'runtime_patch.py') $executable
    if ($LASTEXITCODE -ne 0) { throw "Runtime patch failed with exit code $LASTEXITCODE" }
    Write-Host $patchOutput
}

function Move-GameWindowToLandscapeDisplay(
    [Diagnostics.Process]$process, [int]$windowWidth, [int]$windowHeight
) {
    Add-Type -AssemblyName System.Windows.Forms
    $screen = [System.Windows.Forms.Screen]::AllScreens |
        Where-Object { $_.WorkingArea.Width -ge (1.5 * $_.WorkingArea.Height) } |
        Sort-Object @{ Expression = { $_.WorkingArea.Width * $_.WorkingArea.Height }; Descending = $true } |
        Select-Object -First 1
    if (-not $screen) {
        Write-Warning 'No landscape monitor was found; leaving the game on its default display.'
        return
    }

    if (-not ('LocalDev.LandscapeWindow' -as [type])) {
        Add-Type @'
using System;
using System.Runtime.InteropServices;
namespace LocalDev {
  public static class LandscapeWindow {
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  }
}

'@
    }

    $deadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 200
        $process.Refresh()
    } while (-not $process.HasExited -and $process.MainWindowHandle -eq 0 -and (Get-Date) -lt $deadline)
    if ($process.HasExited -or $process.MainWindowHandle -eq 0) {
        Write-Warning 'Could not find the game window to move it to the landscape monitor.'
        return
    }

    $area = $screen.WorkingArea
    $x = $area.X + [Math]::Max(0, [int](($area.Width - $windowWidth) / 2))
    $y = $area.Y + [Math]::Max(0, [int](($area.Height - $windowHeight) / 2))
    $SWP_NOSIZE = 0x0001
    $SWP_NOZORDER = 0x0004
    $SWP_SHOWWINDOW = 0x0040
    [void][LocalDev.LandscapeWindow]::SetWindowPos(
        $process.MainWindowHandle, [IntPtr]::Zero, $x, $y, 0, 0,
        ($SWP_NOSIZE -bor $SWP_NOZORDER -bor $SWP_SHOWWINDOW))
    [void][LocalDev.LandscapeWindow]::SetForegroundWindow($process.MainWindowHandle)
    Write-Host "Moved game window to landscape display $($screen.DeviceName)."
}

function Set-BorderlessLandscapeWindow(
    [Diagnostics.Process]$process, [int]$renderWidth, [int]$renderHeight
) {
    Add-Type -AssemblyName System.Windows.Forms
    $screen = [System.Windows.Forms.Screen]::AllScreens |
        Where-Object { $_.Bounds.Width -ge (1.5 * $_.Bounds.Height) } |
        Sort-Object @{ Expression = { $_.Bounds.Width * $_.Bounds.Height }; Descending = $true } |
        Select-Object -First 1
    if (-not $screen) { throw 'No landscape monitor was found for borderless mode.' }
    if ($renderWidth -ne $screen.Bounds.Width -or $renderHeight -ne $screen.Bounds.Height) {
        throw "Borderless render size ${renderWidth}x${renderHeight} must match landscape display $($screen.Bounds.Width)x$($screen.Bounds.Height)."
    }

    if (-not ('LocalDev.BorderlessWindow' -as [type])) {
        Add-Type @'
using System;
using System.Runtime.InteropServices;
namespace LocalDev {
  public static class BorderlessWindow {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll", SetLastError=true)] public static extern int GetWindowLong(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll", SetLastError=true)] public static extern int SetWindowLong(IntPtr hWnd, int nIndex, int value);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  }
}
'@
    }

    $deadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 200
        $process.Refresh()
    } while (-not $process.HasExited -and $process.MainWindowHandle -eq 0 -and (Get-Date) -lt $deadline)
    if ($process.HasExited -or $process.MainWindowHandle -eq 0) {
        throw 'Could not find the game window for borderless mode.'
    }

    $GWL_STYLE = -16
    $windowFrameStyles = 0x00CF0000
    $style = [LocalDev.BorderlessWindow]::GetWindowLong($process.MainWindowHandle, $GWL_STYLE)
    [void][LocalDev.BorderlessWindow]::SetWindowLong(
        $process.MainWindowHandle, $GWL_STYLE, ($style -band (-bnot $windowFrameStyles)))
    $bounds = $screen.Bounds
    [void][LocalDev.BorderlessWindow]::SetWindowPos(
        $process.MainWindowHandle, [IntPtr]::Zero,
        $bounds.X, $bounds.Y, $bounds.Width, $bounds.Height,
        (0x0004 -bor 0x0020 -bor 0x0040))
    [void][LocalDev.BorderlessWindow]::SetForegroundWindow($process.MainWindowHandle)

    $client = New-Object LocalDev.BorderlessWindow+RECT
    [void][LocalDev.BorderlessWindow]::GetClientRect($process.MainWindowHandle, [ref]$client)
    $clientWidth = $client.Right - $client.Left
    $clientHeight = $client.Bottom - $client.Top
    if ($clientWidth -ne $renderWidth -or $clientHeight -ne $renderHeight) {
        throw "Borderless client ${clientWidth}x${clientHeight} does not match render ${renderWidth}x${renderHeight}."
    }
    Write-Host "Borderless fullscreen on landscape display $($screen.DeviceName)."
}

function Install-MapForEditor([string]$mapNameOrPath) {
    if (-not $mapNameOrPath) { return $null }
    $mapsDir = Get-UserMapsDirectory
    $source = $null
    if (Test-Path -LiteralPath $mapNameOrPath -PathType Leaf) {
        $source = (Resolve-Path -LiteralPath $mapNameOrPath).Path
    } else {
        $generated = Join-Path $RepoRoot "tools\prompt-to-map\maps\out\$mapNameOrPath.map"
        $installed = Join-Path $mapsDir "$mapNameOrPath\$mapNameOrPath.map"
        if (Test-Path -LiteralPath $generated) {
            $source = $generated
        } elseif (Test-Path -LiteralPath $installed) {
            $source = $installed
        } else {
            throw "Could not find map '$mapNameOrPath' as a file, generated map, or installed user map."
        }
    }

    $installedRoot = [IO.Path]::GetFullPath($mapsDir).TrimEnd('\') + '\'
    $sourceFull = [IO.Path]::GetFullPath($source)
    $workflow = Join-Path $RepoRoot 'tools\prompt-to-map\map_workflow.py'
    if ($sourceFull.StartsWith($installedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        & python $workflow inspect $sourceFull | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Map validation failed with exit code $LASTEXITCODE" }
        return $sourceFull
    }

    $backupDir = Join-Path $LocalRoot 'map-backups'
    $installOutput = @(& python $workflow install $sourceFull $mapsDir --backup-dir $backupDir)
    if ($LASTEXITCODE -ne 0) { throw "Map installation failed with exit code $LASTEXITCODE" }
    if ($installOutput.Count -lt 1) { throw 'Map installer did not return a destination path.' }
    if ($installOutput.Count -gt 1) {
        $installOutput[0..($installOutput.Count - 2)] | ForEach-Object { Write-Host $_ }
    }
    return $installOutput[-1]
}

function Unpack-References([object]$state) {
    $output = Join-Path $LocalRoot 'reference'
    & python (Join-Path $RepoRoot 'tools\prompt-to-map\reference_catalog.py') $state.gameDir $output
    if ($LASTEXITCODE -ne 0) { throw "Reference unpack failed with exit code $LASTEXITCODE" }
    Write-Host "Retail map/INI references are available under $output"
}

function Test-Setup([object]$state) {
    $checks = [ordered]@{
        'Retail game data' = Test-Path (Join-Path $state.gameDir 'INIZH.big')
        'Maintained game executable' = Test-Path (Join-Path $state.runtimeDir 'generalszh.exe')
        'Retail WorldBuilder' = Test-Path (Join-Path $state.gameDir 'WorldBuilder.exe')
        'Python' = [bool](Get-Command python -ErrorAction SilentlyContinue)
        'Sample mod manifest' = Test-Path (Join-Path $RepoRoot 'mods\local-dev\mod.json')
    }
    $checks.GetEnumerator() | ForEach-Object {
        $mark = if ($_.Value) { '[OK]' } else { '[MISSING]' }
        Write-Host "$mark $($_.Key)"
    }
    if ($checks.Values -contains $false) { throw 'One or more local-development checks failed.' }
    $modPath = Build-Mod $state
    Write-Host "[OK] Sample mod archive: $modPath"
    Write-Host "[OK] Runtime release: $($state.release)"
}

$state = if ($Action -eq 'setup') { Install-Runtime } else { Get-State }
Apply-RuntimePatches $state

switch ($Action) {
    'setup' { Test-Setup $state }
    'check' { Test-Setup $state }
    'build' { Build-Mod $state | Out-Null }
    'unpack' { Unpack-References $state }
    'play' {
        if ($Windowed -and $Borderless) { throw 'Choose either -Windowed or -Borderless.' }
        if ($Borderless -and ($XRes -gt 0 -or $YRes -gt 0)) {
            throw 'Borderless mode uses the landscape monitor native resolution; omit -XRes and -YRes.'
        }
        $resolution = Get-WidescreenResolution
        $usesWindow = $Windowed -or $Borderless
        $displayMode = if ($usesWindow) { '-win' } else { '-fullscreen' }
        $arguments = @('-quickstart', $displayMode, '-xres', "$($resolution.Width)",
                       '-yres', "$($resolution.Height)")
        if ($usesWindow) {
            # The maintained executable needs the explicit Windows cursor path in
            # windowed mode; otherwise the pointer can be invisible on this setup.
            Sync-WindowedCursorAssets $state
            $arguments += '-winCursors'
        }
        $modeName = if ($Borderless) { 'borderless fullscreen' } elseif ($Windowed) { 'windowed' } else { 'fullscreen' }
        Write-Host "Display: $($resolution.Width)x$($resolution.Height) $modeName ($($resolution.Device))"
        if (-not $Vanilla) {
            $modPath = Build-Mod $state
            $arguments += @('-mod', ('"{0}"' -f $modPath))
            Write-Host "Launching with mod: $modPath"
        } else {
            Write-Host 'Launching without a mod.'
        }
        $process = Start-Process -FilePath (Join-Path $state.runtimeDir 'generalszh.exe') `
            -ArgumentList $arguments -WorkingDirectory $state.gameDir -PassThru
        Write-Host "Game process started (PID $($process.Id))."
        if ($Borderless) {
            Set-BorderlessLandscapeWindow $process $resolution.Width $resolution.Height
        } elseif ($Windowed) {
            Move-GameWindowToLandscapeDisplay $process $resolution.Width $resolution.Height
        }
        if ($Wait) { $process.WaitForExit(); exit $process.ExitCode }
    }
    'editor' {
        # The release WorldBuilderZH currently expects an in-place install. The owned retail
        # editor is stable with this data layout and keeps the game installation untouched.
        $mapPath = Install-MapForEditor $Map
        $editorArgs = if ($mapPath) { @(('"{0}"' -f $mapPath)) } else { @() }
        $process = Start-Process -FilePath (Join-Path $state.gameDir 'WorldBuilder.exe') `
            -ArgumentList $editorArgs -WorkingDirectory $state.gameDir -PassThru
        Write-Host "WorldBuilder process started (PID $($process.Id))."
        if ($mapPath) { Write-Host "Opened map: $mapPath" }
        if ($Wait) { $process.WaitForExit(); exit $process.ExitCode }
    }
}
