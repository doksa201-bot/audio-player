# Aural Deck

JetAudio의 전통적인 재생기 배치를 참고한 독립적인 데스크톱 오디오 플레이어입니다. MP3, WAV, WMA 파일과 페이드 인·아웃을 지원합니다.

## Windows 실행 파일 만들기

Windows PC에서 Python 3.11을 설치한 다음 PowerShell에서 다음을 실행합니다.

```powershell
./build_windows.ps1
```

완성 파일은 `dist\AuralDeck\AuralDeck.exe`입니다. 폴더 전체를 함께 옮겨야 합니다. WMA 변환용 FFmpeg는 `imageio-ffmpeg` 패키지의 플랫폼별 실행 파일을 함께 포함합니다.

GitHub에서 `v`로 시작하는 태그를 푸시하면 `.github/workflows/windows-release.yml`이 Windows에서 세 가지 형식과 페이드를 검사하고 ZIP 실행 파일을 Release에 올립니다. 수동 실행 시에는 GitHub Actions의 `AuralDeck-Windows-x64` 아티팩트로 결과를 확인할 수 있습니다.

## 소스에서 실행

Python 3.11 이상이 필요합니다. WMA 변환용 FFmpeg는 의존 패키지에 포함됩니다.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

`파일 추가` 버튼이나 파일 드래그로 곡을 넣습니다. `재생`은 기본적으로 페이드 인하며, `정지`와 `페이드 아웃` 버튼은 설정한 시간에 걸쳐 음량을 낮춥니다. 페이드 시간은 0~10초입니다. 곡 마지막에도 가능한 경우 자동으로 페이드 아웃합니다. WMA 변환 파일은 앱 종료 시 임시 폴더와 함께 삭제됩니다.

## 구현 범위

- MP3, WAV, WMA 파일 재생 및 재생목록
- 이전 곡, 재생·일시정지, 정지, 다음 곡, 탐색, 음량 조절
- 페이드 인·아웃 시간 조절 및 수동 페이드 버튼
- 곡 끝에서 자동 페이드 아웃, 다음 곡 자동 재생

Windows 실행 파일은 Windows PC에서 `build_windows.ps1`로 생성합니다. 현재 개발 환경이 macOS라 Windows 실행 파일 자체의 동작 확인은 Windows에서 진행해야 합니다.
