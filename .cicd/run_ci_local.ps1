param (
    [string]$ImageName = "zigbee-ci",
    [string]$CicdDir = ".cicd",
    [string[]]$Flows = @("build")
)

$ErrorActionPreference = "Stop"

Write-Host "Building Docker image from $CicdDir..."
docker build -t $ImageName .\$CicdDir

# Get absolute repo path
$RepoPath = (Get-Location).Path

foreach ($flow in $Flows) {
    Write-Host "Running flow: $flow"

    docker run --rm `
        -v "${RepoPath}:/workspace" `
        -w /workspace `
        $ImageName `
        bash -c "set -e; python3 .cicd/ci_run_flow.py $flow"
}

Write-Host "CI run complete."
