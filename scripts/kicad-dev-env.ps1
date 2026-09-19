# Dot-source this to run the integration tests against a local KiCad build:
#
#   . .\scripts\kicad-dev-env.ps1
#   python -m pytest
#
# It sets KICAD_CLI and puts the build's DLL directories on PATH (a build tree's kicad-cli.exe
# will not start without them). Pass -Build to point at a different KiCad build directory.
#
# Directories that contain a python.exe are skipped: the build tree bundles its own Python, and
# putting it on PATH would hide the Python that has pytest installed.
param([string]$Build = (Join-Path $PSScriptRoot "..\..\kicad\build"))

$install = Join-Path $Build "install\msvc-win64-release\bin"
$dllDirs = Get-ChildItem (Join-Path $Build "msvc-win64-release") -Recurse -Filter *.dll |
    ForEach-Object { $_.DirectoryName } | Sort-Object -Unique |
    Where-Object { -not (Test-Path (Join-Path $_ "python.exe")) }
$env:PATH = "$install;" + ($dllDirs -join ";") + ";" + $env:PATH
$env:KICAD_CLI = Join-Path $install "kicad-cli.exe"
Write-Host "KICAD_CLI = $env:KICAD_CLI"
