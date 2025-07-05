# 📑 드랍쉬핑 자동화 시스템 — PRD v1.0

작성 : 2025‑07‑04  |  담당 : Claude GPT

---

## 0. 개요

- **목표**  : 여러 공급사(API · Excel · 크롤링) 상품을 *수집* → *AI 가공* → *다중 마켓* (API · Excel) 업로드 및 주문·송장 처리까지 **완전 자동화**.
- **핵심 원칙**
  1. **모듈화 & 확장성** – 공급사·마켓·AI 모델을 핫스왑
  2. **원본 보존** – `products_raw.raw_json` (JSONB) 무손실 저장
  3. **증분 처리** – 최신순 → 과거 방향, 일 1회 동기화
  4. **멀티 계정** – 마켓별 여러 셀러 계정 지원
  5. **AI 에이전트** – 로컬(Ollama) + 클라우드(Gemini Flash) 하이브리드

---

## 1. 시스템 디렉터리 구조

```text
 dropshipping/
 ├─ suppliers/            # 공급사 Fetcher/Parser
 │  ├─ base/
 │  ├─ domeme/
 │  ├─ ownerclan/
 │  └─ zentrade/
 ├─ sourcing/             # 내부 판매/경쟁사/네이버 MCP
 │  ├─ self_sales/
 │  ├─ competitor/
 │  └─ scorer/
 ├─ transformers/         # 표준 Product 변환
 ├─ storage/              # Supabase handler
 ├─ ai_processors/        # 상품명·옵션·이미지 가공
 ├─ uploader/             # 마켓 업로드 (API·Excel)
 │  ├─ coupang_api/
 │  ├─ elevenst_api/
 │  ├─ smartstore_api/
 │  ├─ gmarket_excel/
 │  └─ auction_excel/
 ├─ scheduler/            # APScheduler / Cron
 ├─ mcp/                  # Gemini CLI · model‑sync 등
 ├─ db/                   # schema.sql · seed SQL
 ├─ tests/                # Pytest
 └─ main.py               # 파이프라인 엔트리
```

---

## 2. 데이터베이스 스키마 (Supabase PostgreSQL)

| 범주          | 테이블                                                              | 목적 요약           |
| ----------- | ---------------------------------------------------------------- | --------------- |
| **메타**      | `suppliers`, `marketplaces`, `market_accounts`, `model_registry` | 공급사·마켓·계정·AI 모델 |
| **상품**      | `products_raw`, `products_processed`, `product_listings`         | 원본·가공본·마켓 매핑    |
| **카테고리·규칙** | `category_mappings`, `pricing_rules`                             | 카테고리·가격 공식      |
| **로그**      | `ingestion_logs`, `processing_logs`, `upload_logs`               | 파이프라인 추적        |
| **소싱**      | `sales_products`, `competitor_products`, `sourcing_candidates`   | 내부 매출·경쟁사·후보군   |

> **DDL 파일** : `db/schema.sql`\
> **Seed** : `db/seed_suppliers.sql` – 초기 공급사 4행(domeme, ownerclan, zentrade, excel\_generic)

---

## 3. 핵심 워크플로우

1. **Fetch (Ingestion)** : Domeme 목록→상세, Ownerclan 1k 배치→상세, Zentrade 전체 XML(≈20 MB)
2. **Store Raw** → `products_raw`
3. **Transform** → `StandardProduct` JSON
4. **AI Processing** : 상품명, HTML 정제, 이미지 캡처·배경 제거, 가격 결정
5. **Save Processed** → `products_processed`
6. **Upload**  (API : 쿠팡·11번가·스마트스토어 / Excel : G마켓·옥션)\
      계정별 큐·리트라이 → `product_listings`, `upload_logs`
7. **Order & Tracking** : 주문 Excel 업·다운로드, Ownerclan API 발송
8. **Sourcing** (병렬) : 내부 베스트셀러 / 경쟁사 크롤링 / 네이버 MCP 키워드 → `sourcing_candidates` 스코어 후 재주입
9. **Monitoring** : Slack Webhook 오류 알림, Grafana 대시

---

## 4. AI / MCP 전략

| 레이어            | 엔진                                                                       | 대표 모델                                    | 용도                         |
| -------------- | ------------------------------------------------------------------------ | ---------------------------------------- | -------------------------- |
| **로컬(Ollama)** | RTX 4070                                                                 | Gemma 3n QAT, DeepSeek‑R1 7B, Qwen 3 14B | 빠른 상품명·HTML→JSON·이미지 캡션    |
| **클라우드**       | Gemini 2.5 Flash Mini / Flash                                            |  –                                       | 대량 키워드·SEO 제목 생성           |
| **라우터**        | `agent_router.py`                                                        |  –                                       | 작업 난도·비용에 따른 모델 자동 선택      |
| **MCP 도구**     | `ollama-model-sync`, `schema-builder`, `supplier-test`, `agent-pipeline` |  –                                       | 모델 레지스트리, DB 스키마 관리, 배치 실행 |

---

## 5. 환경 변수 (.env)

`SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY` 및 마켓·API 키;  `.gitignore` 에 `.env` 포함하여 Git 노출 방지.

---

## 6. Git 플로우

| 브랜치                | 설명                                            |
| ------------------ | --------------------------------------------- |
| `main`             | 운영 / 배포                                       |
| `dev`              | 통합 개발                                         |
| `feature/<module>` | 기능 단위(`fetcher-domeme`, `uploader‑coupang` 등) |
| `release/vX.Y.Z`   | 버전 태그                                         |

커밋 컨벤션 예 : `feat(db): add products_processed table`

---

## 7. 단계별 로드맵

| Phase | 목표                                 | 핵심 산출물                                                                    |
| ----- | ---------------------------------- | ------------------------------------------------------------------------- |
| **1** | DB 스키마 & 환경 파일                     | `schema.sql`, `.env.example`, `supabase_handler.py`, `seed_suppliers.sql` |
| **2** | `BaseFetcher` + Domeme Fetcher MVP | `suppliers/base/`, `suppliers/domeme/`, 테스트                               |
| **3** | Category Mapper & Pricing Rule MVP | `category_mapper.py`, `pricing_rules` seed                                |
| **4** | Uploader 인터페이스 + 쿠팡 API MVP        | `uploader/base_uploader.py`, `uploader/coupang_api/`                      |
| **5** | AI Processor MVP (상품명·HTML)        | `ai_processors/name_enhancer.py` …                                        |
| **6** | Sourcing 모듈(내부·경쟁사·MCP)            | `sourcing/*`, `scorer/ranker.py`                                          |
| **7** | 모델 레지스트리 MCP & Agent Router        | `model_registry` 테이블, `agent_router.py`                                   |
| **8** | 주문/송장 + 모니터링 대시                    | `order_jobs/`, `tracking_logs`, Grafana 보드                                |

---

## 8. 비‑기능 요구사항

| 영역      | 기준                                      |
| ------- | --------------------------------------- |
| **성능**  | 10 k SKU 증분 < 30 min                    |
| **확장성** | 신규 공급사·마켓 모듈 추가 ≤ 2 일                   |
| **보안**  | Supabase RLS : `credential_json` 행단위 보호 |
| **가용성** | 크리티컬 배치 실패 즉시 Slack 알림                  |
| **비용**  | 클라우드 AI 모델 비용 월 \$50 이내(가격 가드)          |

---

## 9. 리스크 & 대응

| 리스크               | 영향             | 대응                             |
| ----------------- | -------------- | ------------------------------ |
| 공급사 API 구조 변경     | Fetch 중단       | `supplier-test` MCP 주기 검사 · 알림 |
| 마켓 정책 변경 (이미지·제목) | 노출↓ / 계정 정지 위험 | 정책 템플릿·AI 리포맷 신속 롤백            |
| 대량 크롤링 차단         | 경쟁사 데이터 부족     | IP Pool·지연·캐시                  |
| AI 모델 비용 폭증       | 운영비 증가         | Router 가격 가드 + Usage 모니터링      |

---

## 10. 부록

### 10.1 Playbooks

- 새 모델 릴리스 → 모델 sync MCP 자동 pull → Slack 알림
- DB 마이그레이션 → `schema.sql` 버전 관리 → CI 자동 적용

### 10.2 테스트 전략

- Pytest + Mock API & Playwright 픽스처

### 10.3 DEV vs PROD

- Supabase 프로젝트 2개, `.env.dev` / `.env.prod` 스위칭

---

### ✅ 즉시 실행 TODO

1. Claude Code 브랜치 `feature/db-schema` 생성   → **Phase 1 구현**
2. `schema.sql`, `.env.example`, `supabase_handler.py`, `seed_suppliers.sql` 파일 자동 생성 → 커밋
3. Supabase DDL + Seed 실행 → 테이블 16종 및 `suppliers` 4행 확인
4. ✔ 끝나면 **Phase 2 – BaseFetcher MVP** 진행

---

## Phase 2 — BaseFetcher & Domeme Fetcher MVP

### 2‑1. 목표

- **공통 Fetcher 인터페이스**(`BaseFetcher`) 정의 → 모든 공급사가 상속.
- **Domeme(도매매) Fetcher** 구현 : 목록 API + 상세 API 연동.
- 원본 데이터를 `products_raw` 테이블에 저장하고, 해시 중복 체크.
- 기본 단위 테스트(Pytest) 통과.

### 2‑2. 산출물

| ID   | 파일/디렉터리                            | 설명                                         |
| ---- | ---------------------------------- | ------------------------------------------ |
| F2‑1 | `suppliers/base/base_fetcher.py`   | 추상 클래스 (싱글톤 세션, hash 계산, insert\_raw)      |
| F2‑2 | `suppliers/domeme/fetcher.py`      | Domeme 목록 → 상세 → `insert_raw` 호출           |
| F2‑3 | `suppliers/domeme/test_fetcher.py` | Pytest : 실제 API mock · 목록 10개 페치 시 성공 확인   |
| F2‑4 | `tests/conftest.py`                | 공통 fixture : Supabase 테스트 DB, HTTP mocking |

### 2‑3. 상세 기능 명세

1. **BaseFetcher**
   - `fetch_list(page:int) -> list[dict]` (abstract)
   - `fetch_detail(item_id:str) -> dict` (abstract)
   - `run_incremental(since:datetime)` : 최신순 반복 호출·중복 해시 필터
   - 내부 메서드 `save_raw(json_obj)` → `products_raw` insert, 해시(unique) 충돌 시 skip.
2. **Domeme Fetcher**
   - 목록 API 엔드포인트 `searchProductList` (ver 4.1)
   - 상세 API `searchProductInfo` (ver 4.5)
   - 페이지 당 100 → 최신순; `market=supply` 파라미터 적용.
   - `since` 파라미터 미지원 → 응답 `reg_date` 비교 후 중단.
3. **에러 처리** 
   - 5xx / 타임아웃 시 3회 재시도, 로그는 `ingestion_logs`.
4. **테스트 기준** 
   - 목록 Mock → 10개 상품, 상세 Mock → XML 샘플 1개.
   - `run_incremental()` 실행 후 `products_raw` 10행 생성 + 중복 호출 시 행 수 증가 0.

### 2‑4. 구현 순서 (Claude Code TODO)

| 단계 | 브랜치                      | 작업                                        |
| -- | ------------------------ | ----------------------------------------- |
| 1  | `feature/base-fetcher`   | F2‑1 추상 클래스 구현 + 테스트 스텁                   |
| 2  | `feature/domeme-fetcher` | F2‑2 Fetcher 코드 + F2‑3 테스트                |
| 3  | `feature/domeme-fetcher` | 로컬 .env Domeme API KEY 확인 후 실통합 Smoke 테스트 |
| 4  | PR → `dev`               | 리뷰·병합                                     |

### 2‑5. 검수 체크리스트

- `suppliers/base/base_fetcher.py` : ABC + run\_incremental 구현
- Domeme 목록 100 → → 상세 1:1 → `products_raw` insert OK
- 중복 해시 스킵 동작 확인(Pytest)
- 실패 로그 `ingestion_logs` 기록

---

## Phase 3 — Category Mapper & Pricing Rule MVP

### 3‑1. 목표

- 공급사 카테고리 코드 → 마켓별 카테고리 코드 매핑 테이블 완성.
- 단순 가격 규칙(JSON 공식) 설계 → `price_final` 계산 가능.

### 3‑2. 산출물

| ID   | 파일/테이블                          | 설명                         |
| ---- | ------------------------------- | -------------------------- |
| F3‑1 | `mapper/category_mapper.py`     | 공급사 코드 → 마켓 코드 변환기 (캐시 포함) |
| F3‑2 | `pricing_rules` seed SQL        | 기본 룰 (원가×1.35 + 3,000)     |
| F3‑3 | `tests/test_category_mapper.py` | Pytest : 매핑 5건 → 기대 결과     |

### 3‑3. 기능 명세

1. `get_market_code(supplier_code:str, market:str) -> str`
2. `apply_pricing(cost:int, rule_id:int) -> int`

### 3‑4. 구현 TODO

1. `feature/category-mapper` 브랜치 → F3‑1 구현
2. `feature/pricing-rule` 브랜치 → F3‑2 seed 작성
3. 통합 PR → `dev`

---

## Phase 4 — Uploader Interface & 쿠팡 API MVP

### 4‑1. 목표

- 업로더 공통 추상 클래스(`BaseUploader`) 설계.
- 쿠팡 API 상품 등록 / 재고 수정 / 가격 수정 엔드포인트 연동.

### 4‑2. 산출물

| ID   | 파일                                 | 설명                            |
| ---- | ---------------------------------- | ----------------------------- |
| F4‑1 | `uploader/base_uploader.py`        | 공통 메서드 (upload, stock, price) |
| F4‑2 | `uploader/coupang_api/uploader.py` | 쿠팡 전용 구현                      |
| F4‑3 | `tests/test_coupang_uploader.py`   | Mock API 테스트                  |

### 4‑3. 구현 TODO

1. `feature/base-uploader` 브랜치 → F4‑1
2. `feature/uploader-coupang` 브랜치 → F4‑2 + F4‑3
3. Smoke 테스트 : 샘플 상품 1건 업로드 → 응답 코드 200

---

## Phase 5 — AI Processor MVP (상품명·HTML·이미지)

### 5‑1. 목표

- 상품명 AI 가공 (`name_enhancer.py`) : 트렌드 키워드 반영.
- 상세 HTML Sanitizer + 불필요 태그 제거.
- 이미지를 Supabase Storage 업로드 + URL 치환.

### 5‑2. 산출물

| ID   | 파일                               | 설명                    |
| ---- | -------------------------------- | --------------------- |
| F5‑1 | `ai_processors/name_enhancer.py` | 로컬 LLM → 제목 생성        |
| F5‑2 | `ai_processors/html_cleaner.py`  | BeautifulSoup 기반 정제   |
| F5‑3 | `ai_processors/image_handler.py` | 배경 제거 (SD ControlNet) |

---

## Phase 6 — Sourcing 모듈 (내부 매출·경쟁사·MCP)

### 6‑1. 목표

- 내부 판매 상품 → `sales_products` 동기화.
- 경쟁사 제품 크롤러 + 파서 구현.
- 네이버 MCP 키워드 기반 후보군 수집.

### 6‑2. 산출물

| 파일                                  | 설명              |
| ----------------------------------- | --------------- |
| `sourcing/self_sales/sync_sales.py` | 마켓 API → DB 스냅샷 |
| `sourcing/competitor/crawler.py`    | Playwright 크롤러  |
| `sourcing/scorer/ranker.py`         | 수요·경쟁·마진 스코어링   |

---

## Phase 7 — 모델 레지스트리 MCP & Agent Router

### 7‑1. 목표

- Ollama 라이브러리 최신 모델 → `model_registry` 자동 sync.
- `agent_router.py` : 작업 유형별 모델·비용 정책.

### 7‑2. 산출물

| 파일                         | 설명                 |
| -------------------------- | ------------------ |
| `mcp/ollama-model-sync.js` | Smithery CLI용 스크립트 |
| `agent_router.py`          | 모델 선택 로직 + 가격 가드   |

---

## Phase 8 — 주문·송장 처리 & 모니터링

### 8‑1. 목표

- 주문 Excel 자동 다운로드·업로드, Ownerclan 주문 API 연동.
- 송장 번호 업데이트 → 각 마켓 API / Excel.
- Grafana 대시보드 + Slack 알림.

### 8‑2. 산출물

| 파일                             | 설명             |
| ------------------------------ | -------------- |
| `order_jobs/order_sync.py`     | 주문 → 도매처 엑셀 발주 |
| `order_jobs/tracking_sync.py`  | 송장 업데이트        |
| `monitoring/grafana_dash.json` | KPI 대시 구성      |
| `monitoring/slack_alert.py`    | 실패 알림 모듈       |

---

## 11. Claude Code × Gemini CLI 협업 가이드 (토큰 절감)

### 11‑1. 원칙

1. **Claude Code ⟶ 지휘관** : 요구사항·설계·리뷰·요약 담당.
2. **Gemini CLI ⟶ 실무자** : 대용량 코드 생성·분석·리팩터.
3. **MCP Router** : 코드 >200 라인 생성/분석 → Gemini CLI, 그 외 Claude.
4. **Diff 전달** : Claude에는 전체 파일 대신 *변경 diff*만 보내 토큰 최소화.

### 11‑2. 워크플로우 예

| 단계 | 작업                | 담당         | 토큰 절감 팁                      |
| -- | ----------------- | ---------- | ---------------------------- |
| 1  | 기능 설계·PRD 작성      | Claude     | 요약 텍스트만 사용                   |
| 2  | 스켈레톤 코드 생성        | Gemini CLI | `gemini run gen-skeleton …`  |
| 3  | 코드 리뷰             | Claude     | `git diff` 범위만 입력            |
| 4  | 대규모 리팩터 (>300 라인) | Gemini CLI | `gemini -e refactor file.py` |
| 5  | 최종 요약·커밋 메시지      | Claude     | 200자 이내 메시지                  |

### 11‑3. MCP tool 설정 예 (`claude_code_config.json`)

```json
{
  "tools": [
    {
      "id": "gemini",
      "name": "Gemini CLI",
      "entry": "npx -y @google/gemini-cli",
      "args": ["--model=gemini-2.5-flash-mini"],
      "env": { "GEMINI_API_KEY": "${GEMINI_API_KEY}" }
    }
  ],
  "router": {
    "rules": [
      { "if": "lines>200 || file_size>51200", "tool": "gemini" },
      { "else": "claude" }
    ]
  }
}
```

### 11‑4. 운영 체크리스트

-

---

