# End-to-end batch runner (PowerShell).
#
#   .\tools\eval\run_all.ps1                # default N=15 per profile
#   $env:N=2; .\tools\eval\run_all.ps1      # smoke test
param(
    [int]$N = $(if ($env:N) { [int]$env:N } else { 15 }),
    [string]$Godot = $(if ($env:GODOT) { $env:GODOT } else { "C:\Users\wasif\Downloads\Godot_v4.6.2-stable_win64.exe\Godot_v4.6.2-stable_win64_console.exe" })
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $Root

$Profiles = @("aggressive", "cautious", "explorer", "completionist")
$UserDir = Join-Path $env:APPDATA "Godot\app_userdata\Agentic Quest Generator"
$EvalDir = Join-Path $UserDir "eval"

New-Item -ItemType Directory -Force -Path $EvalDir, "tools\eval\sessions", "tools\eval\results" | Out-Null
Remove-Item -Force "$EvalDir\*.jsonl" -ErrorAction SilentlyContinue
Remove-Item -Force "tools\eval\sessions\*.jsonl" -ErrorAction SilentlyContinue

$total = $N * $Profiles.Count
$i = 0
foreach ($profile in $Profiles) {
    for ($run = 1; $run -le $N; $run++) {
        $i++
        Write-Host "[$i/$total] profile=$profile run=$run"
        $env:AGQ_EVAL = "1"
        $env:AGQ_PROFILE = $profile
        & $Godot --headless --path . "res://scenes/EvalSession.tscn" *>&1 | Out-Null
        Start-Sleep -Seconds 1
    }
}

Copy-Item -Force "$EvalDir\*.jsonl" "tools\eval\sessions\" -ErrorAction SilentlyContinue
Copy-Item -Force "$EvalDir\entities.json" "tools\eval\" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Aggregating metrics..."
python tools\eval\runner.py `
    --in tools\eval\sessions `
    --out tools\eval\results `
    --entities tools\eval\entities.json

Write-Host ""
Write-Host "Done. See tools\eval\results\{results.json, results.csv, summary.json}"
