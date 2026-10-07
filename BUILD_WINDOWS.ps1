param(
    [Parameter(Mandatory = $true)]
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildEnvironment = Join-Path $RepoRoot ".build-venv"
$BuildDirectory = Join-Path $RepoRoot ".build-output-final"
Push-Location $RepoRoot
try {
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        throw "Python executable not found: $PythonPath"
    }

    $PythonVersion = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not run Python at $PythonPath"
    }
    $VersionParts = $PythonVersion.Trim().Split('.')
    $Major = [int]$VersionParts[0]
    $Minor = [int]$VersionParts[1]
    if (($Major -lt 3) -or (($Major -eq 3) -and ($Minor -lt 10))) {
        throw "Python 3.10 or newer is required. Found Python $PythonVersion."
    }

    if (-not (Test-Path -LiteralPath $BuildEnvironment)) {
        & $PythonPath -m venv $BuildEnvironment
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the isolated build environment."
        }
    }
    $BuildPython = Join-Path $BuildEnvironment "Scripts\python.exe"
    & $BuildPython -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install the build dependency. See the pip output above."
    }

    & $BuildPython -m PyInstaller `
        --noconfirm `
        --onefile `
        --windowed `
        --name BioDetective `
        --distpath dist `
        --workpath $BuildDirectory `
        --specpath $BuildDirectory `
        main.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    Write-Host "BioDetective executable created: $RepoRoot\dist\BioDetective.exe"
}
finally {
    Pop-Location
}

