$ErrorActionPreference = "Stop"

Write-Host "Starting Pulse-Chennai Demo..."

if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
}

$env:VIRTUAL_ENV = "$PWD\venv"
$env:PATH = "$PWD\venv\Scripts;$env:PATH"

Write-Host "Installing Python dependencies..."
python -m pip install -r requirements.txt -q

Write-Host "Starting backend server..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location `"$PWD`"; `$env:VIRTUAL_ENV=`"$PWD\venv`"; `$env:PATH=`"$PWD\venv\Scripts;`$env:PATH`"; uvicorn api.dashboard_server:app --host 0.0.0.0 --port 8000"

Start-Sleep -Seconds 2

Write-Host "Seeding stop data..."
python seed_stops.py

Write-Host "Starting bus simulator..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location `"$PWD`"; `$env:VIRTUAL_ENV=`"$PWD\venv`"; `$env:PATH=`"$PWD\venv\Scripts;`$env:PATH`"; python -m simulator.demo_simulation"

Write-Host "Starting frontend..."
if (Test-Path "frontend") {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location `"$PWD\frontend`"; npm install -q; npm run dev"
}

Write-Host ""
Write-Host "Pulse-Chennai is starting up!"
Write-Host "  Backend:   http://localhost:8000"
Write-Host "  Frontend:  http://localhost:5173"
Write-Host "  Simulator: Running"
Write-Host "Three new PowerShell windows have been opened for the Backend, Simulator, and Frontend."
Write-Host "Close those windows to stop the services."
