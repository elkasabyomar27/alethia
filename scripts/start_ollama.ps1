# Start only this project's portable runtime; settings apply to this process.
$ErrorActionPreference = 'Stop'
$alethiaRoot = Split-Path -Parent $PSScriptRoot
$alethiaRuntime = Join-Path $alethiaRoot 'models\ollama-runtime\v0.40.11\runtime\ollama.exe'
if (-not (Test-Path -LiteralPath $alethiaRuntime)) { throw 'Run scripts/prepare_ollama_runtime.py first.' }
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = Join-Path $alethiaRoot 'models\ollama'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NOHISTORY = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_MAX_QUEUE = '1'
$env:OLLAMA_KEEP_ALIVE = '0'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
& $alethiaRuntime serve
