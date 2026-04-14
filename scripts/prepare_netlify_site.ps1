param(
    [string]$PortableZipPath = "",
    [string]$ReportHtmlPath = "docs/PROJECT_REVIEW_REPORT_6_CHAPTERS.html"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$siteRoot = Join-Path $repoRoot "netlify_site"
$downloadsDir = Join-Path $siteRoot "downloads"
$reportDir = Join-Path $siteRoot "report"

New-Item -ItemType Directory -Force -Path $downloadsDir | Out-Null
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

$resolvedReport = Join-Path $repoRoot $ReportHtmlPath
if (Test-Path $resolvedReport) {
    Copy-Item -Force $resolvedReport (Join-Path $reportDir "PROJECT_REVIEW_REPORT_6_CHAPTERS.html")
}

if ([string]::IsNullOrWhiteSpace($PortableZipPath)) {
    $candidate = Get-ChildItem (Join-Path $repoRoot "releases") -Filter "MiningMaintenanceSystem_Portable_*.zip" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($candidate) {
        $PortableZipPath = $candidate.FullName
    }
}

if (-not [string]::IsNullOrWhiteSpace($PortableZipPath) -and (Test-Path $PortableZipPath)) {
    Copy-Item -Force $PortableZipPath (Join-Path $downloadsDir "MiningMaintenanceSystem_Portable.zip")
    Write-Host "Copied portable zip to netlify_site/downloads."
} else {
    Write-Host "Portable zip not copied. Provide -PortableZipPath or place a release zip in /releases."
}

Write-Host "Netlify site prepared at: $siteRoot"
Write-Host "Deploy command (from repo root): netlify deploy --prod --dir=netlify_site"
