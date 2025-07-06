# CLAUDE.md


## Claude MCP 연동 지침

- Claude CLI는 MCP 서버로 로컬에서 실행되며, 기본 포트는 `8181`입니다.
- MCP 설정은 `claude_code_config.json`에 명시되어 있으며, `defaultTool`은 `claude`입니다.
- Gemini CLI로 생성된 코드에 대해서는 Claude가 자동 리뷰를 수행합니다 (`autoReview: true`).
- MCP 도구 ID는 `claude`, 내부 실행 명령은 `node ./tools/claude-mcp-server.mjs`입니다.
- Claude는 기본 응답자이며, 모든 자연어 프롬프트 요청은 Claude MCP로 전달됩니다.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

한국어로 대답해줘.

## Project Overview

**드랍쉬핑 자동화 시스템** - 공급사 상품 수집 → AI 가공 → 마켓플레이스 업로드 → 주문 관리의 전체 워크플로우를 자동화하는 Python 3.11+ 기반 시스템입니다.

### 핵심 특징
- **비동기 아키텍처**: httpx/asyncio 기반 고성능 처리
- **AI 파이프라인**: Ollama(로컬) + Gemini(클라우드) 하이브리드
- **다중 플랫폼**: 여러 공급사/마켓플레이스 동시 지원
- **완전 자동화**: 스케줄러 기반 24/7 운영
- **프로덕션 준비**: Docker, systemd, 모니터링 완비

## Commands

### 초기 설정
```bash
# 가상환경 및 의존성
source activate.sh             # 가상환경 활성화
pip install -r requirements.txt # 의존성 설치
cp .env.example .env           # 환경 변수 설정 (수정 필요)

# 데이터베이스 초기화
python db/migrate.py           # 스키마 마이그레이션
python db/seed_data.py         # 초기 데이터 로드
```

### 개발 명령어
```bash
# CLI 인터페이스
python -m dropshipping.main    # 대화형 CLI 실행

# 공급사 상품 수집
python -m dropshipping.main fetch --supplier domeme              # Domeme 수집
python -m dropshipping.main fetch --supplier ownerclan           # 오너클랜 수집
python -m dropshipping.main fetch --supplier zentrade            # Zentrade 수집
python -m dropshipping.main fetch --supplier domeme --dry-run    # 테스트 모드

# AI 처리
python -m dropshipping.main process                              # 전체 AI 처리
python -m dropshipping.main process --model ollama              # 로컬 모델만 사용
python -m dropshipping.main process --model gemini              # Gemini만 사용

# 마켓플레이스 업로드
python -m dropshipping.main upload --marketplace coupang         # 쿠팡 업로드
python -m dropshipping.main upload --marketplace elevenst        # 11번가 업로드
python -m dropshipping.main upload --marketplace smartstore      # 스마트스토어
python -m dropshipping.main upload --marketplace gmarket         # G마켓 Excel

# 자동화
python -m dropshipping.main schedule                             # 스케줄러 실행
python -m dropshipping.main monitor                              # 모니터링 대시보드

# API 서버
uvicorn dropshipping.api.main:app --reload                      # 개발 서버
uvicorn dropshipping.api.main:app --host 0.0.0.0 --port 8000   # 프로덕션
```

### 테스트
```bash
# 기본 테스트
pytest                          # 전체 테스트
pytest -v                       # 상세 출력
pytest -s                       # print 문 출력
pytest -x                       # 첫 실패시 중단
pytest --lf                     # 마지막 실패 테스트만

# 커버리지
pytest --cov=dropshipping                    # 커버리지 측정
pytest --cov=dropshipping --cov-report=html  # HTML 리포트

# 특정 테스트
pytest tests/suppliers/test_domeme.py        # 특정 파일
pytest -k "test_fetch"                       # 이름 패턴
pytest -m "slow"                             # 마커별 실행
```

### 코드 품질
```bash
# 포맷팅 & 린팅
black dropshipping tests        # 코드 포맷팅
ruff check dropshipping tests   # 린팅 검사
ruff check --fix               # 자동 수정
mypy dropshipping              # 타입 검사

# 통합 검사
make lint                      # black + ruff + mypy
make format                    # 자동 포맷팅
```

## Architecture

### 핵심 설계 원칙
1. **추상 기반 클래스** - 모든 주요 컴포넌트는 Base* 클래스 상속으로 일관성 유지
2. **의존성 주입** - 생성자를 통한 설정 주입으로 테스트 용이성 확보
3. **데이터 보존** - 원본 응답을 JSONB로 저장하여 디버깅/재처리 가능
4. **점진적 처리** - 최신 항목 우선 처리, 중단 후 재개 가능
5. **오류 복원력** - 지수 백오프 재시도, 부분 실패 허용

### 모듈 구조
```
dropshipping/
├── suppliers/         # 공급사 통합 (BaseFetcher 구현체)
│   ├── domeme/       # 도매매/도매꾹 API (XML)
│   ├── ownerclan/    # 오너클랜 GraphQL API  
│   ├── zentrade/     # 젠트레이드 대량 XML
│   └── excel/        # 범용 Excel 지원
├── transformers/      # 원본 데이터 → StandardProduct 변환
├── storage/           # 데이터 영속성 계층
│   ├── supabase_storage.py  # Supabase PostgreSQL
│   └── json_storage.py      # 로컬 JSON 백업
├── ai_processors/     # AI 가공 파이프라인
│   ├── product_enhancer.py  # 상품명/설명 최적화
│   ├── image_processor.py   # 이미지 캡션, 배경 제거
│   └── model_router.py      # 예산/복잡도별 모델 선택
├── uploader/          # 마켓플레이스 통합 (BaseUploader)
│   ├── coupang.py    # 쿠팡 WING OpenAPI
│   ├── elevenst.py   # 11번가 XML + OAuth
│   ├── smartstore.py # 스마트스토어 Commerce API v2
│   └── gmarket_excel.py # G마켓 ESM Plus Excel
├── orders/            # 주문 생명주기 관리
├── sourcing/          # 시장 분석 도구
├── scheduler/         # 작업 자동화
├── monitoring/        # 시스템 상태 & 알림
├── api/              # FastAPI REST 서버
├── models/            # Pydantic 데이터 모델
├── domain/            # 비즈니스 로직 (가격, 검증)
├── mcp/              # Model Context Protocol 도구
├── db/               # 데이터베이스 관리
│   ├── schema.sql    # PostgreSQL 스키마 (16개 테이블 + RLS)
│   ├── seed_data.sql # 초기 데이터
│   └── migrate.py    # 마이그레이션 도구
└── tests/            # 포괄적 테스트 스위트
```

### 데이터 플로우
1. **수집**: Fetcher → 원본 JSON (products_raw 테이블)
2. **변환**: Transformer → StandardProduct 형식
3. **가공**: AI Processors → 최적화된 상품 데이터
4. **업로드**: Uploader → 마켓플레이스별 형식
5. **모니터링**: 주문 동기화 → 재고 업데이트 → 알림

### 핵심 클래스와 인터페이스
- `BaseFetcher`: 모든 공급사 통합의 추상 클래스
- `BaseTransformer`: 공급사 데이터를 표준 형식으로 변환
- `BaseUploader`: 모든 마켓플레이스 통합의 추상 클래스
- `BaseAIProcessor`: AI 처리 파이프라인 인터페이스
- `StandardProduct`: 모든 상품의 공통 데이터 모델
- `ModelRouter`: 작업/예산에 따른 최적 AI 모델 선택
- `SupplierRegistry`: 동적 공급사 등록 시스템
- `UploaderRegistry`: 동적 마켓플레이스 업로더 등록

## Common Tasks

### 새 공급사 추가
1. `dropshipping/suppliers/new_supplier/` 디렉토리 생성
2. `fetcher.py`에서 `BaseFetcher` 상속 구현
3. `transformer.py`에서 `BaseTransformer` 상속 구현
4. `tests/suppliers/test_new_supplier.py`에 테스트 추가
5. `suppliers/registry.py`에 `@SupplierRegistry.register()` 데코레이터로 등록

### 새 마켓플레이스 추가
1. `dropshipping/uploader/new_marketplace.py` 파일 생성
2. `BaseUploader` 클래스 상속
3. 필수 메서드 구현: `upload_product()`, `check_upload_status()`
4. `.env`에 마켓플레이스 설정 추가
5. `tests/uploader/test_new_marketplace.py`에 테스트 추가
6. `uploader/registry.py`에 `@UploaderRegistry.register()` 데코레이터로 등록

### 디버깅 팁
- `logs/` 디렉토리의 로그 확인 (loguru 순환 파일)
- 원본 API 응답은 `products_raw.raw_json` 컬럼에 저장됨
- `pytest -s`로 테스트 중 print 문 확인
- `.env`에서 `LOG_LEVEL=DEBUG`로 상세 로깅 활성화
- 중단점 사용: `import pdb; pdb.set_trace()`
- VS Code 디버거 설정: `launch.json`에 설정 추가

## 환경 변수 (.env)
```bash
# 환경 설정
ENVIRONMENT=development  # development, staging, production, test

# 데이터베이스
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your-anon-key

# AI 모델
OPENAI_API_KEY=sk-xxx              # GPT-4 (선택사항)
GEMINI_API_KEY=xxx                 # Gemini Pro (필수)
OLLAMA_HOST=http://localhost:11434 # 로컬 LLM (권장)
AI_MAX_MONTHLY_BUDGET=1000         # 월 최대 예산 ($)
AI_MAX_COST_PER_ITEM=0.1          # 상품당 최대 비용 ($)

# 공급사 API
DOMEME_API_KEY=xxx                 # 도매매/도매꾹
OWNERCLAN_TOKEN=xxx                # 오너클랜
ZENTRADE_FTP_USER=xxx              # 젠트레이드 FTP
ZENTRADE_FTP_PASS=xxx

# 마켓플레이스 API
COUPANG_ACCESS_KEY=xxx             # 쿠팡 WING
COUPANG_SECRET_KEY=xxx
ELEVENST_API_KEY=xxx               # 11번가
SMARTSTORE_CLIENT_ID=xxx           # 스마트스토어
SMARTSTORE_CLIENT_SECRET=xxx

# 모니터링
SLACK_WEBHOOK_URL=https://hooks.slack.com/xxx

# 처리 설정
BATCH_SIZE=100                     # 배치 크기
MAX_CONCURRENT_REQUESTS=10         # 동시 요청 수
RETRY_ATTEMPTS=3                   # 재시도 횟수
RETRY_DELAY=1                      # 재시도 대기(초)
```

## 테스트 전략
- **단위 테스트**: 외부 의존성(API, DB) 모킹
- **통합 테스트**: 테스트 DB 사용, 테스트 계정으로 실제 API 호출
- **픽스처**: `conftest.py`의 공통 테스트 데이터
- **테스트 격리**: 각 테스트는 트랜잭션 내에서 실행, 종료 후 롤백
- **커버리지 목표**: 80% 이상 유지

## 데이터베이스 테이블
주요 테이블 구조:
- **메타데이터**: suppliers, marketplaces, seller_accounts, ai_models
- **상품**: products_raw, products_processed, product_variants, products_ai_enhanced
- **마켓플레이스**: marketplace_listings
- **비즈니스 규칙**: category_mappings, pricing_rules
- **주문/재고**: orders, inventory_sync_logs
- **소싱**: keyword_research, competitor_products
- **시스템**: pipeline_logs

각 테이블은 RLS(Row Level Security) 정책과 적절한 인덱스를 포함합니다.

## 문제 해결
- **Import 오류**: 프로젝트 루트에서 실행, `PYTHONPATH` 확인
- **DB 오류**: Supabase 연결 확인, 마이그레이션 실행
- **API 속도 제한**: 지수 백오프 구현, 배치 작업 사용
- **메모리 문제**: 청크 단위 처리, 대용량 데이터셋에 제너레이터 사용
- **비동기 오류**: 독립 스크립트에서 `asyncio.run()` 사용
- **레지스트리 오류**: 데코레이터 사용법 확인 (`@SupplierRegistry.register()`)

## 개발 도구
- **Poetry 지원**: `pyproject.toml` 파일 (pip와 병행 사용 가능)
- **Pre-commit 훅**: 코드 품질 자동 검사
- **Python 버전**: 3.11+ 필수 (3.12 권장)
- **IDE 설정**: VS Code 설정 파일 포함 (.vscode/)