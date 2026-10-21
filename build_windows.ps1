$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if ($env:OS -ne 'Windows_NT') {
    throw '이 빌드 스크립트는 Windows에서 실행해야 합니다.'
}

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.11 -m venv .venv
}

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $python -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw '패키지 설치에 실패했습니다.' }

& $python -m PyInstaller --noconfirm --clean --windowed --onedir --name AuralDeck --collect-all imageio_ffmpeg main.py
if ($LASTEXITCODE -ne 0) { throw '실행 파일 빌드에 실패했습니다.' }

Write-Host "완료: $PSScriptRoot\dist\AuralDeck\AuralDeck.exe"
