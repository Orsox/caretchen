param(
    [string]$PythonExe = "py",
    [string]$PythonSelector = "-3.11"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-Python {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Args
    )

    if ([string]::IsNullOrWhiteSpace($PythonSelector)) {
        & $PythonExe @Args
    }
    else {
        & $PythonExe $PythonSelector @Args
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $PythonExe $PythonSelector $($Args -join ' ')"
    }
}

Push-Location $RepoRoot
try {
    $pythonVersion = if ([string]::IsNullOrWhiteSpace($PythonSelector)) {
        & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    }
    else {
        & $PythonExe $PythonSelector -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Python runtime could not be started."
    }

    $pythonVersion = $pythonVersion.Trim()
    if ([Version]$pythonVersion -lt [Version]"3.11") {
        throw "Python 3.11 or newer is required, but detected $pythonVersion."
    }

    Invoke-Python -- -m pip install -U pip
    Invoke-Python -- -m pip install -e ".[dev]"

    Invoke-Python -- -m PyInstaller `
      --noconfirm `
      --onefile `
      --windowed `
      --name DictaPaste `
      --collect-submodules faster_whisper `
      --collect-submodules ctranslate2 `
      src/dictapaste/main.py
}
finally {
    Pop-Location
}
