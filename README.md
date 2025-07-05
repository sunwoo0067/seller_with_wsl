# 드랍쉬핑 자동화 시스템

여러 공급사의 상품을 수집하여 AI로 가공한 후 다중 마켓플레이스에 자동으로 업로드하는 완전 자동화 시스템입니다.

## 📋 프로젝트 구조

```
dropshipping/
├── suppliers/         # 공급사 Fetcher/Parser
├── sourcing/          # 내부 판매/경쟁사 분석
├── transformers/      # 데이터 표준화
├── storage/           # 데이터베이스 핸들러
├── ai_processors/     # AI 상품 가공
├── uploader/          # 마켓플레이스 업로더
├── scheduler/         # 작업 스케줄러
├── mcp/              # Model Context Protocol
├── db/               # 데이터베이스 스키마
└── tests/            # 테스트 코드
```

## 🚀 시작하기

### 1. 환경 설정

```bash
# Python 3.11+ 필요
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 필요한 API 키 설정
```

### 3. 테스트 실행

```bash
pytest
```

## 🛠️ 개발 로드맵

### ✅ Step 1: 기초 인프라 (완료)
- [x] Python 프로젝트 초기화
- [x] 디렉터리 구조 생성
- [x] Git 설정
- [x] 환경 변수 관리
- [x] 설정 로더 구현
- [x] 테스트 환경 구축

### 🔄 Step 2: 데이터 모델 (진행중)
- [ ] StandardProduct 데이터 클래스
- [ ] 데이터 변환 인터페이스
- [ ] Mock 데이터 생성기

### 📅 향후 계획
- Step 3: BaseFetcher 추상화
- Step 4: 도메인 로직 (가격/카테고리)
- Step 5: 첫 번째 API 통합 (Domeme)
- Step 6: 데이터베이스 통합 (Supabase)
- Step 7: AI 처리 파이프라인
- Step 8: 마켓플레이스 업로더

## 📝 주요 기능

- **모듈화 & 확장성**: 공급사/마켓/AI 모델 핫스왑 가능
- **원본 보존**: JSONB 형태로 무손실 저장
- **증분 처리**: 최신순 → 과거 방향 동기화
- **멀티 계정**: 마켓별 여러 셀러 계정 지원
- **AI 하이브리드**: 로컬(Ollama) + 클라우드(Gemini) 조합

## 🔧 개발 도구

```bash
# 코드 포맷팅
black dropshipping tests

# 린팅
ruff check dropshipping tests

# 타입 체크
mypy dropshipping

# 테스트 커버리지
pytest --cov=dropshipping
```

## 📚 참고 문서

- [PRD v1.0](docs/dropshipping_prd_v_1.md)
- [API 문서](docs/)

## 📄 라이선스

Private - All rights reserved