# SMART 4 취업서류 준비 현황 대시보드

Google Drive의 학생별 취업서류 폴더를 조회해 GitHub Pages에서 확인할 수 있는 정적 대시보드입니다.

## 구성

- `index.html`, `styles.css`, `app.js`: GitHub Pages로 배포되는 대시보드
- `data/config.json`: 조회할 문서 유형 설정
- `data/manual-status.json`: 조기 취업 학생 ID 목록
- `data/dashboard-data.json`: 현재 대시보드 데이터
- `data/history/`: 시간별 데이터 스냅샷
- `scripts/fetch_drive_status.py`: Google Drive 조회 및 JSON 생성 스크립트
- `.github/workflows/update-dashboard-data.yml`: 1시간 자동 갱신 및 수동 실행 워크플로

## GitHub Secrets

저장소 Settings > Secrets and variables > Actions에 아래 값을 등록합니다.

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `GOOGLE_DRIVE_ROOT_FOLDER_ID`

상위 Drive 폴더 ID는 `1XGjLEPcehFm_aCgoxBlADyiji5gynQ9I`입니다.

## GitHub Pages

저장소 Settings > Pages에서 Source를 `GitHub Actions`로 설정합니다. 이후 `main` 브랜치에 push되면 `.github/workflows/deploy-pages.yml`이 대시보드를 배포합니다.

## 로컬 실행

```bash
python -m http.server 8000
```

브라우저에서 `http://localhost:8000`을 엽니다.

## 데이터 갱신

```bash
pip install -r requirements.txt
python scripts/fetch_drive_status.py
```

OAuth refresh token이 필요하면 Google OAuth 클라이언트의 `credentials.json`을 저장소 루트에 둔 뒤 아래 명령으로 발급합니다.

```bash
python scripts/generate_oauth_token.py
```
