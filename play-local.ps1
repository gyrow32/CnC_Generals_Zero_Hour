param(
    [switch]$Vanilla,
    [switch]$Windowed,
    [switch]$Fullscreen,
    [int]$XRes = 0,
    [int]$YRes = 0
)

if ($Windowed -and $Fullscreen) {
    throw 'Choose either -Windowed or -Fullscreen, not both.'
}
$Borderless = -not $Windowed -and -not $Fullscreen

& "$PSScriptRoot\tools\local-dev\dev.ps1" -Action play -Vanilla:$Vanilla `
    -Windowed:$Windowed -Borderless:$Borderless -XRes $XRes -YRes $YRes
