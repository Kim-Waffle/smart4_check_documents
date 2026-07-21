# 취업서류 준비 현황 대시보드 요구사항

## 목적

Google Drive 상위 폴더 아래의 학생별 취업서류 준비 현황을 수집하여 GitHub Pages 기반 웹 대시보드로 표시한다.

## 확정 조건

- 배포 위치: GitHub 저장소 `Kim-Waffle/smart4_check_documents`
- 배포 형태: GitHub Pages 정적 웹페이지, Source는 GitHub Actions
- 데이터 갱신: GitHub Actions로 1시간마다 자동 실행, `workflow_dispatch`로 수동 실행
- 인증 방식: Google OAuth refresh token 기반 Drive 조회
- 상위 Drive 폴더 ID: `1XGjLEPcehFm_aCgoxBlADyiji5gynQ9I`
- 대시보드 공개 범위: URL을 아는 사용자가 접근 가능
- 공개 가능 정보: 학생 이름, 파일명, 수정일, 폴더 링크

## Drive 폴더 구조

상위 폴더 바로 아래의 각 폴더를 학생 1명으로 본다. 학생 이름은 폴더명을 그대로 사용한다.

각 학생 폴더 아래에는 다음 하위 폴더가 있다고 가정한다.

- 입사지원서
- 포트폴리오
- 면접자료

## 문서 유형 설정

문서 유형은 코드에 직접 하드코딩하지 않고 `data/config.json`에서 관리한다.

```json
{
  "documentTypes": [
    {
      "id": "application",
      "label": "입사지원서",
      "folderName": "입사지원서",
      "showChart": true
    },
    {
      "id": "portfolio",
      "label": "포트폴리오",
      "folderName": "포트폴리오",
      "showChart": true
    },
    {
      "id": "interview",
      "label": "면접자료",
      "folderName": "면접자료",
      "showChart": false
    }
  ]
}
```

`showChart`를 `true`로 바꾸면 추후 면접자료 그래프도 쉽게 추가할 수 있다.

## 수집 기준

- 각 문서 폴더 안에 파일이 하나라도 있으면 `작성`
- 파일이 없으면 `미작성`
- 최근 파일은 마지막 수정일자가 가장 최근인 파일
- 파일 형식은 제한하지 않는다.
- 링크는 폴더명/파일명이 아니라 Google Drive ID 기반 URL로 저장한다.

## 조기 취업 상태

- 조기 취업은 학생 단위 상태로 관리한다.
- 조기 취업 학생은 모든 문서 유형 그래프에서 `조기 취업` 항목으로 집계한다.
- 공식 공유 상태는 `data/manual-status.json`의 `earlyEmployedStudentIds`에 저장한다.
- 공개 GitHub Pages 화면의 토글은 보안상 GitHub 저장소에 직접 쓰지 않고, 현재 브라우저의 localStorage에만 즉시 반영한다.

## 그래프 요구사항

상단에는 `showChart: true`인 문서 유형별 원형 그래프를 표시한다.

각 그래프는 전체 학생 중 다음 비율을 표시한다.

- 작성
- 미작성
- 조기 취업

초기 표시 그래프는 다음 2개다.

- 입사지원서
- 포트폴리오

## 학생 카드 및 모달

대시보드 하단에는 학생별 카드를 표시한다. 카드를 선택하면 모달 팝업을 연다.

모달에서 확인할 정보:

- 학생 폴더 링크
- 문서 유형별 폴더 링크
- 문서 유형별 작성 상태
- 최근 파일명
- 최근 파일 링크
- 최근 수정일자
- 조기 취업 상태 전환 버튼

## 필터 및 정렬

다음 기능을 제공한다.

- 학생 이름 검색
- 문서 유형 필터
- 작성 / 미작성 / 조기 취업 상태 필터
- 이름 오름차순/내림차순 정렬
- 최근 수정일 최신순/오래된순 정렬

## 데이터 파일

현재 상태:

```text
data/dashboard-data.json
```

변경 이력:

```text
data/history/YYYY-MM-DD-HHMM.json
```

대시보드는 기본적으로 현재 상태 JSON만 읽는다. 이력 JSON은 추후 추이 분석 기능에 활용할 수 있다.

## GitHub Actions Secrets

다음 Secrets를 저장소에 등록한다.

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `GOOGLE_DRIVE_ROOT_FOLDER_ID`

## 향후 확장 포인트

- 면접자료 그래프 표시
- 문서별 상세 제출 추이
- 학생별 변경 이력 비교
- 관리자 전용 조기 취업 상태 저장 기능
- 비공개 대시보드 또는 접근 제한 배포
