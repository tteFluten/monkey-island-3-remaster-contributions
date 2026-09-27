param([string]$BasementRoot = 'E:\basement.lab')
$ErrorActionPreference = 'Stop'
$source = Join-Path $BasementRoot 'confite'
Push-Location $source
try {
    & node 'node_modules/vite/bin/vite.js' build --mode sprite
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar Confite.' }
} finally { Pop-Location }
$compiled = Join-Path $BasementRoot 'artifacts/monkey-sprite-painter-build/confite/index.html'
$destination = Join-Path $PSScriptRoot 'confite'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item -LiteralPath $compiled -Destination (Join-Path $destination 'index.html') -Force
Write-Host 'Confite actualizado. Recargá el taller cuando hayas guardado tus cambios.'
