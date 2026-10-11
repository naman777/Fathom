# Build the full EnterpriseRAG-Bench index (about 512k documents, 2.65M chunks, roughly 6 hours on an RTX 3050).
#
#   powershell -ExecutionPolicy Bypass -File scripts\ingest_full.ps1
#
# Loads into the collection "enterprise_full" so the development index in "enterprise" keeps serving the demo.
# Safe to run again: it resumes from the checkpoint next to the dataset. Progress goes to D:\fathom-data\ingest_full.log.
# Needs: Docker Desktop running with the fathom-qdrant container, the dataset in D:\fathom-data\erb, and the GPU
# environment in D:\fathom-data\venv-ml. Keep the laptop plugged in with the lid open.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:DOCKER_HOST = $null  # a machine-level DOCKER_HOST points the CLI at a dead port; Docker Desktop's context works
$env:HF_HOME = "D:\fathom-data\hf-cache"
$env:FASTEMBED_CACHE_PATH = "D:\fathom-data\fastembed-cache"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

docker --context desktop-linux start fathom-qdrant | Out-Null
for ($i = 0; $i -lt 30; $i++) {
    try { Invoke-WebRequest http://localhost:6333/healthz -UseBasicParsing -TimeoutSec 3 | Out-Null; break } catch { Start-Sleep -Seconds 2 }
}

$log = "D:\fathom-data\ingest_full.log"
"=== started $(Get-Date -Format s) ===" | Add-Content $log
cmd /c "D:\fathom-data\venv-ml\Scripts\python.exe -m enterprise.ingest --collection enterprise_full --batch 64 >> $log 2>&1"
"=== exited $(Get-Date -Format s) with code $LASTEXITCODE ===" | Add-Content $log
