param(
    [string]$PythonExe = "py",
    [string]$PythonSelector = "-3.11"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path $PSScriptRoot).Path

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
    Invoke-Python -- -m dictapaste.main
}
finally {
    Pop-Location
}
