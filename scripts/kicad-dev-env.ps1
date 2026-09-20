# Dot-source to run the integration tests against a local KiCad build: . .\scripts\kicad-dev-env.ps1
# Sets KICAD_CLI and puts the build's DLL directories on PATH (-Build overrides the build directory).
# Directories containing a python.exe are skipped so the build's bundled Python does not hide the one with pytest.
param([string]$Build = (Join-Path $PSScriptRoot "..\..\kicad\build"))

$install = Join-Path $Build "install\msvc-win64-release\bin"
$dllDirs = Get-ChildItem (Join-Path $Build "msvc-win64-release") -Recurse -Filter *.dll |
    ForEach-Object { $_.DirectoryName } | Sort-Object -Unique |
    Where-Object { -not (Test-Path (Join-Path $_ "python.exe")) }
$env:PATH = "$install;" + ($dllDirs -join ";") + ";" + $env:PATH
$env:KICAD_CLI = Join-Path $install "kicad-cli.exe"
Write-Host "KICAD_CLI = $env:KICAD_CLI"
