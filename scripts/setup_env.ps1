$ErrorActionPreference = "Stop"

$venvDir = "venv"
$reqFile = "scripts/requirements.txt"

if (-not (Test-Path $venvDir)) {
  Write-Host "📦 Creo ambiente virtuale in $venvDir ..."
  python -m venv $venvDir
} else {
  Write-Host "📦 Ambiente virtuale gia presente: $venvDir"
}

. ".\$venvDir\Scripts\Activate.ps1"

Write-Host "⬆️  Installo dipendenze da $reqFile ..."
python -m pip install -r $reqFile

Write-Host "✅ Ambiente pronto e attivo ($((python --version) 2>&1))"
Write-Host "💡 Per riattivarlo in futuro: .\venv\Scripts\Activate.ps1"
