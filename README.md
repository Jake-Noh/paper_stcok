# 📦 SCM 운영재고 자동 산출 시스템

제지회사 SCM팀을 위한 데이터 기반 안전재고 산출 플랫폼.

## 기능

- **운영재고 자동 산출** — 안전재고(독립/종속) + 사이클재고 수식 기반
- **엑셀 업로드** — 판매 실적·리드타임 실적 일괄 입력
- **현재고 입력·발주 산출** — 현재고 대비 발주 필요량 자동 계산
- **ML 수요예측** — EMA + 선형회귀(GDP 반영) 참고 지표
- **5가지 비즈니스 룰** — 샘플 부족·트렌드·이상치 자동 검증
- **ECOS API 연동** — 한국은행 GDP 성장률 수집

## Streamlit Cloud 배포

### 1. GitHub에 이 폴더를 리포지토리로 업로드

### 2. [share.streamlit.io](https://share.streamlit.io) 접속 후 배포

| 항목 | 값 |
|---|---|
| Repository | `<your-github-repo>` |
| Branch | `main` |
| Main file path | `app.py` |

### 3. Secrets 설정 (선택)

Streamlit Cloud 대시보드 → **Secrets** 탭에 입력:

```toml
ECOS_API_KEY = "한국은행_ECOS_API_키"
```

> API 키 없이도 앱이 동작합니다. GDP 데이터는 기본값(2.5%)으로 대체됩니다.

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8601
```

## 파일 구조

```
├── app.py                  # 메인 진입점
├── requirements.txt
├── .streamlit/
│   └── config.toml
├── core/                   # 통계·재고 계산 엔진
├── data/                   # DB (SQLite) 및 스키마
├── ml/                     # 수요예측·ECOS 클라이언트
├── ui/                     # 페이지별 UI 모듈
└── utils/                  # 유효성 검사·내보내기
```

## 주의사항

Streamlit Cloud는 **세션 종료 시 DB가 초기화**됩니다.  
데이터를 영구 보존하려면 외부 DB(PostgreSQL 등)로 전환이 필요합니다.
