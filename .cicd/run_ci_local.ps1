param (
    [string]$ImageName = "zigbee-ci",
    [string]$CicdDir = ".cicd"
)

$ErrorActionPreference = "Stop"

Write-Host "Building Docker image..."
docker build -t $ImageName .\$CicdDir

Write-Host "Running CI inside container..."

# Get absolute repo path
$RepoPath = (Get-Location).Path

docker run --rm `
    -v "${RepoPath}:/workspace" `
    -w /workspace `
    $ImageName `
    bash -c "set -e;
        python3 .cicd/ci_build.py
    "

Write-Host "CI run complete."
