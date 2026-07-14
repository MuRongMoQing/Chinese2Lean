[CmdletBinding()]
param(
    [string]$Repository = 'https://github.com/MuRongMoQing/Chinese2Lean.git',
    [string]$Target = (Join-Path (Get-Location) 'Chinese2Lean'),
    [string]$Branch = 'main',
    [string]$ExpectedCommit = '',
    [string]$PythonCommand = 'python',
    [string]$PythonExtras = 'dev,api',
    [string]$SmokeLeanFile = 'examples/generated/positive_add_one.lean',
    [ValidateRange(1, 10)]
    [int]$CacheAttempts = 3,
    [switch]$SkipMathlibCache,
    [switch]$SkipValidation,
    [switch]$RepositoryOnly,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-NativeCaptured {
    param(
        [Parameter(Mandatory)]
        [scriptblock]$Command
    )

    $previousPreference = $ErrorActionPreference
    $output = ''
    $exitCode = 1
    try {
        # Windows PowerShell 5.1 turns redirected native stderr into error records.
        # Normalize those records and decide success only from the process exit code.
        $ErrorActionPreference = 'Continue'
        $records = @(& $Command 2>&1)
        $exitCode = $LASTEXITCODE
        $output = (($records | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $_.Exception.Message
            }
            else {
                $_.ToString()
            }
        }) -join [Environment]::NewLine).Trim()
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    [pscustomobject]@{
        Output = $output
        ExitCode = $exitCode
    }
}

function Assert-CommandAvailable {
    param(
        [Parameter(Mandatory)]
        [string]$Name
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command is not available on PATH: $Name"
    }
}

function Get-RequiredCommands {
    param(
        [Parameter(Mandatory)]
        [string]$PythonName,
        [switch]$WithoutMathlibCache
    )

    $commands = @('git.exe', $PythonName, 'elan.exe', 'lake.exe')
    if (-not $WithoutMathlibCache) {
        $commands += @('curl.exe', 'tar.exe')
    }
    return $commands
}

function Get-ValidationChecks {
    return @(
        [pscustomobject]@{
            Name = 'pytest'
            Arguments = @('-m', 'pytest')
            FailureMessage = 'pytest failed'
        }
        [pscustomobject]@{
            Name = 'ruff'
            Arguments = @('-m', 'ruff', 'check', '.')
            FailureMessage = 'Ruff failed'
        }
        [pscustomobject]@{
            Name = 'mypy'
            Arguments = @('-m', 'mypy', 'src')
            FailureMessage = 'mypy failed'
        }
        [pscustomobject]@{
            Name = 'verify-all'
            Arguments = @('-m', 'chinese2lean.cli', 'verify-all', 'examples/generated')
            FailureMessage = 'Lean batch verification failed'
        }
        [pscustomobject]@{
            Name = 'version'
            Arguments = @('-m', 'chinese2lean.cli', 'version')
            FailureMessage = 'Version report failed'
        }
    )
}

function Get-NormalizedGitPath {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\').Replace('\', '/')
}

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory)]
        [scriptblock]$Command,
        [Parameter(Mandatory)]
        [string]$FailureMessage
    )

    $result = Invoke-NativeCaptured $Command
    if ($result.Output) {
        Write-Host $result.Output
    }
    if ($result.ExitCode -ne 0) {
        throw "$FailureMessage (exit code $($result.ExitCode))"
    }
    return $result
}

function Get-RepositoryStatus {
    param(
        [Parameter(Mandatory)]
        [string]$RepositoryPath
    )

    $result = Invoke-NativeCaptured { git -C $RepositoryPath status --porcelain }
    if ($result.ExitCode -ne 0 -and $result.Output -match 'dubious ownership') {
        $safePath = Get-NormalizedGitPath $RepositoryPath
        $configuredResult = Invoke-NativeCaptured {
            git config --global --get-all safe.directory
        }
        $configured = if ($configuredResult.ExitCode -eq 0) {
            @($configuredResult.Output -split "`r?`n")
        }
        else {
            @()
        }
        if (-not ($configured | Where-Object { $_ -ieq $safePath })) {
            Invoke-CheckedNative {
                git config --global --add safe.directory $safePath
            } "Failed to add exact Git safe.directory entry: $safePath" | Out-Null
            Write-Host "Added exact Git safe.directory entry: $safePath"
        }
        $result = Invoke-NativeCaptured { git -C $RepositoryPath status --porcelain }
    }
    return $result
}

if ($SelfTest) {
    $capture = Invoke-NativeCaptured {
        cmd /c 'echo bootstrap-info 1>&2 & exit /b 0'
    }
    if ($capture.ExitCode -ne 0 -or
        $capture.Output -notmatch 'bootstrap-info' -or
        $capture.Output -match 'NativeCommandError') {
        throw "Native output capture self-test failed: $($capture.Output)"
    }

    $normalized = Get-NormalizedGitPath (Join-Path $env:TEMP 'Chinese2Lean-self-test')
    if ($normalized.Contains('\') -or -not [System.IO.Path]::IsPathRooted($normalized)) {
        throw "Path normalization self-test failed: $normalized"
    }

    Write-Host 'Bootstrap self-test passed.'
    Write-Host "Repository: $Repository"
    Write-Host "Target: $(Get-NormalizedGitPath $Target)"
    Write-Host "Branch: $Branch"
    Write-Host "Expected commit: $ExpectedCommit"
    Write-Host "Python command: $PythonCommand"
    $requiredCommands = @(Get-RequiredCommands `
        -PythonName $PythonCommand `
        -WithoutMathlibCache:$SkipMathlibCache)
    Write-Host "Cache attempts: $CacheAttempts"
    Write-Host "Skip validation: $($SkipValidation.IsPresent)"
    $validationNames = @(
        Get-ValidationChecks | ForEach-Object { $_.Name }
    )
    Write-Host "Required commands: $($requiredCommands -join ', ')"
    Write-Host "Validation checks: $($validationNames -join ', ')"
    exit 0
}

if ($env:OS -ne 'Windows_NT') {
    throw 'This bootstrap script targets Windows PowerShell. Use a platform-specific wrapper elsewhere.'
}

Assert-CommandAvailable 'git.exe'

$Target = [System.IO.Path]::GetFullPath($Target)
$gitDirectory = Join-Path $Target '.git'
Write-Host "Development environment target: $Target"

if (Test-Path -LiteralPath $gitDirectory) {
    Write-Host 'Existing clone detected; validating and resuming.'
}
else {
    if (Test-Path -LiteralPath $Target) {
        $existing = @(Get-ChildItem -Force -LiteralPath $Target)
        if ($existing.Count -ne 0) {
            throw "Target directory is not empty and is not a Git clone: $Target"
        }
    }
    else {
        $parent = Split-Path -Parent $Target
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    Invoke-CheckedNative {
        git clone --branch $Branch --single-branch $Repository $Target
    } 'Git clone failed' | Out-Null
}

$repositoryStatus = Get-RepositoryStatus $Target
if ($repositoryStatus.ExitCode -ne 0) {
    throw "Unable to inspect repository status: $($repositoryStatus.Output)"
}
if ($repositoryStatus.Output) {
    throw "Repository must be clean before bootstrapping:`n$($repositoryStatus.Output)"
}

$originResult = Invoke-NativeCaptured { git -C $Target remote get-url origin }
if ($originResult.ExitCode -ne 0 -or $originResult.Output.Trim() -ne $Repository) {
    throw "Unexpected origin remote: $($originResult.Output)"
}

$branchResult = Invoke-NativeCaptured { git -C $Target rev-parse --abbrev-ref HEAD }
if ($branchResult.ExitCode -ne 0 -or $branchResult.Output.Trim() -ne $Branch) {
    throw "Expected branch '$Branch', found '$($branchResult.Output.Trim())'"
}

Invoke-CheckedNative {
    git -C $Target fetch --prune origin $Branch
} "Unable to fetch origin/$Branch" | Out-Null

$headResult = Invoke-NativeCaptured { git -C $Target rev-parse HEAD }
$remoteHeadResult = Invoke-NativeCaptured {
    git -C $Target rev-parse "refs/remotes/origin/$Branch"
}
if ($headResult.ExitCode -ne 0 -or $remoteHeadResult.ExitCode -ne 0) {
    throw "Unable to compare local HEAD with origin/$Branch."
}
$head = $headResult.Output.Trim()
$remoteHead = $remoteHeadResult.Output.Trim()
if ($head -ne $remoteHead) {
    $ancestorResult = Invoke-NativeCaptured {
        git -C $Target merge-base --is-ancestor $head $remoteHead
    }
    if ($ancestorResult.ExitCode -ne 0) {
        throw "Local branch '$Branch' is ahead of or diverged from origin/$Branch; refusing to overwrite it."
    }
    Invoke-CheckedNative {
        git -C $Target merge --ff-only $remoteHead
    } "Unable to fast-forward '$Branch' to origin/$Branch" | Out-Null
    $head = $remoteHead
}
if ($ExpectedCommit -and -not $head.StartsWith($ExpectedCommit, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Expected HEAD beginning with '$ExpectedCommit', found '$head'"
}

if ($RepositoryOnly) {
    Write-Host ''
    Write-Host 'Repository synchronization passed; environment setup was not run.'
    Write-Host "Workspace: $Target"
    Write-Host "Branch: $Branch"
    Write-Host "HEAD: $head"
    exit 0
}

$requiredCommands = @(Get-RequiredCommands `
    -PythonName $PythonCommand `
    -WithoutMathlibCache:$SkipMathlibCache)
foreach ($requiredCommand in $requiredCommands) {
    Assert-CommandAvailable $requiredCommand
}

Push-Location $Target
try {
    $venvPython = Join-Path $Target '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Invoke-CheckedNative {
            & $PythonCommand -m venv .venv
        } 'Virtual environment creation failed' | Out-Null
    }
    else {
        Write-Host 'Existing virtual environment detected; reusing it.'
    }

    $editableSpec = if ($PythonExtras) { ".[${PythonExtras}]" } else { '.' }
    Invoke-CheckedNative {
        & $venvPython -m pip install -e $editableSpec
    } 'Python dependency installation failed' | Out-Null

    $toolchainFile = Join-Path $Target 'lean-toolchain'
    if (-not (Test-Path -LiteralPath $toolchainFile)) {
        throw "Pinned Lean toolchain file is missing: $toolchainFile"
    }
    $leanToolchain = (Get-Content -Raw -LiteralPath $toolchainFile).Trim()
    if (-not $leanToolchain) {
        throw 'Pinned Lean toolchain file is empty.'
    }

    $leanResult = Invoke-NativeCaptured { lake env lean --version }
    if ($leanResult.ExitCode -ne 0) {
        Write-Host "Pinned Lean is not ready; installing $leanToolchain."
        $installResult = Invoke-NativeCaptured { elan toolchain install $leanToolchain }
        if ($installResult.Output) {
            Write-Host $installResult.Output
        }
        if ($installResult.ExitCode -ne 0 -and $installResult.Output -notmatch 'already installed') {
            Write-Warning "Elan installation returned exit code $($installResult.ExitCode)."
        }
        $leanResult = Invoke-NativeCaptured { lake env lean --version }
    }
    if ($leanResult.Output) {
        Write-Host $leanResult.Output
    }
    if ($leanResult.ExitCode -ne 0) {
        throw "Pinned Lean environment is unavailable: $($leanResult.Output)"
    }

    if (-not $SkipMathlibCache) {
        $mathlibSource = Join-Path $Target '.lake\packages\mathlib\Mathlib.lean'
        if (-not (Test-Path -LiteralPath $mathlibSource)) {
            throw 'Mathlib was not materialized by Lake. Check the pinned manifest and network access.'
        }
        $mathlibOlean = Join-Path $Target '.lake\packages\mathlib\.lake\build\lib\lean\Mathlib.olean'

        if (Test-Path -LiteralPath $mathlibOlean) {
            Write-Host 'Pinned Mathlib build cache is already present; reusing it.'
        }
        else {
            for ($attempt = 1; $attempt -le $CacheAttempts; $attempt++) {
                Write-Host "Downloading the pinned Mathlib build cache (attempt $attempt/$CacheAttempts)."
                $cacheResult = Invoke-NativeCaptured { lake exe cache get }
                if ($cacheResult.Output) {
                    Write-Host $cacheResult.Output
                }
                if (Test-Path -LiteralPath $mathlibOlean) {
                    break
                }
                Write-Warning "Cache attempt $attempt exited with code $($cacheResult.ExitCode)."
                if ($attempt -lt $CacheAttempts) {
                    Start-Sleep -Seconds (5 * $attempt)
                }
            }

            if (-not (Test-Path -LiteralPath $mathlibOlean)) {
                Write-Host 'Collecting verbose ProofWidgets release diagnostics.'
                $proofWidgetsResult = Invoke-NativeCaptured {
                    lake -v build proofwidgets:release
                }
                if ($proofWidgetsResult.Output) {
                    Write-Host $proofWidgetsResult.Output
                }
                if ($proofWidgetsResult.ExitCode -eq 0) {
                    $cacheResult = Invoke-NativeCaptured { lake exe cache get }
                    if ($cacheResult.Output) {
                        Write-Host $cacheResult.Output
                    }
                }
                if (-not (Test-Path -LiteralPath $mathlibOlean)) {
                    throw 'Mathlib cache is unavailable after all retry and diagnostic attempts.'
                }
            }
        }
    }

    $smokePath = Join-Path $Target ($SmokeLeanFile.Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $smokePath)) {
        throw "Lean smoke file does not exist: $smokePath"
    }
    Write-Host "Running Lean smoke compilation: $SmokeLeanFile"
    $smokeResult = Invoke-NativeCaptured { lake env lean $SmokeLeanFile }
    if ($smokeResult.Output) {
        Write-Host $smokeResult.Output
    }
    if ($smokeResult.ExitCode -ne 0 -and -not $SkipMathlibCache) {
        Write-Host 'Smoke compilation failed; forcing one Mathlib cache refresh.'
        $repairResult = Invoke-NativeCaptured { lake exe cache get! }
        if ($repairResult.Output) {
            Write-Host $repairResult.Output
        }
        $smokeResult = Invoke-NativeCaptured { lake env lean $SmokeLeanFile }
        if ($smokeResult.Output) {
            Write-Host $smokeResult.Output
        }
    }
    if ($smokeResult.ExitCode -ne 0) {
        throw "Lean smoke compilation failed with exit code $($smokeResult.ExitCode)"
    }

    if (-not $SkipValidation) {
        foreach ($check in @(Get-ValidationChecks)) {
            $arguments = @($check.Arguments)
            Invoke-CheckedNative {
                & $venvPython @arguments
            } $check.FailureMessage | Out-Null
        }
    }

    Invoke-CheckedNative {
        git diff --exit-code
    } 'Tracked files changed during bootstrap validation' | Out-Null

    $finalStatus = Get-RepositoryStatus $Target
    if ($finalStatus.ExitCode -ne 0 -or $finalStatus.Output) {
        throw "Repository is not clean after bootstrap validation:`n$($finalStatus.Output)"
    }
}
finally {
    Pop-Location
}

Write-Host ''
if ($SkipValidation) {
    Write-Host 'Development environment initialized; full validation was skipped.'
}
else {
    Write-Host 'Development environment bootstrap passed.'
}
Write-Host "Workspace: $Target"
Write-Host "Branch: $Branch"
Write-Host "HEAD: $head"
