# Builds the KiCad PCM plugin zip into dist\ (install it via Plugin and Content Manager >
# "Install from File..."). Extra arguments pass straight to build_package.py:
#
#   .\scripts\build_package.ps1
#   .\scripts\build_package.ps1 --list
#   .\scripts\build_package.ps1 --out-dir C:\temp\out
$script = Join-Path $PSScriptRoot "build_package.py"
$probe = "import sys; sys.exit(sys.version_info < (3, 9))"

# Try each interpreter rather than trust the name: python.exe can be a Microsoft Store stub that fails.
$candidates = @(@("python"), @("python3"), @("py", "-3"))
foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate[0] -ErrorAction SilentlyContinue)) { continue }
    $prefix = @($candidate | Select-Object -Skip 1)
    & $candidate[0] @prefix -c $probe 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $candidate[0] @prefix $script @args
        exit $LASTEXITCODE
    }
}
Write-Error "Python 3.9 or newer was not found on PATH."
exit 1
