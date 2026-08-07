$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildDir = Join-Path $repoRoot "build"
$distDir = Join-Path $repoRoot "dist"
$exeName = "CNKI2WOS_1.0.0_Windows_x64.exe"
$exePath = Join-Path $distDir $exeName

foreach ($candidate in @($buildDir, $exePath)) {
    if (Test-Path -LiteralPath $candidate) {
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        if (-not $resolved.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "拒绝删除仓库之外的路径：$resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

Push-Location $repoRoot
try {
    python -m PyInstaller --clean --noconfirm cnki2wos.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败。" }

    if (Test-Path -LiteralPath $buildDir) {
        $resolvedBuildDir = (Resolve-Path -LiteralPath $buildDir).Path
        if (-not $resolvedBuildDir.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "拒绝删除仓库之外的路径：$resolvedBuildDir"
        }
        Remove-Item -LiteralPath $resolvedBuildDir -Recurse -Force
    }

    $hash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $exeName" | Set-Content -LiteralPath (Join-Path $distDir "SHA256SUMS.txt") -Encoding ascii
    python tools\validate_repository.py --require-dist
    if ($LASTEXITCODE -ne 0) { throw "发布物验证失败。" }
}
finally {
    Pop-Location
}
