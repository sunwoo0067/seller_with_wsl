# gemini.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

한국어로 대답해줘.

# Gemini CLI 도구 사용

대용량 코드 구조나 전체 파일 분석이 필요하면 다음처럼 Gemini CLI 사용:

```tool:gemini
gemini -p "@src/ 전체 코드 구조를 요약해줘"
gemini -p "@src/main.py 이 파일이 하는 역할을 설명해줘"


## Project Overview

This is a **Dropshipping Automation System** that automates the entire workflow from supplier product collection to marketplace listing and order management. The system is fully implemented with 138 passing unit tests.

## Commands

```bash
# 테스트
pytest                          # 전체 테스트 실행
pytest -v                       # 상세 테스트 실행  
pytest --cov=dropshipping      # 커버리지 포함 테스트
pytest tests/test_specific.py  # 특정 테스트 파일 실행

# 코드 포맷팅 및 린팅
black dropshipping tests        # Black 포맷터 실행
ruff check dropshipping tests   # Ruff 린터 실행
mypy dropshipping              # MyPy 타입 검사

# 메인 CLI 실행
python -m dropshipping.main    # CLI 인터페이스

# 개발 환경
source activate.sh             # 가상환경 활성화 (Linux/Mac)
pip install -r requirements.txt # 의존성 설치
```

## Architecture

### Core Principles
1. **Modular & Extensible** - Hot-swappable suppliers, marketplaces, and AI models
2. **Preserve Original Data** - Store raw data in `products_raw.raw_json` (JSONB) without modification
3. **Incremental Processing** - Process newest to oldest, sync once daily
4. **Multi-Account Support** - Multiple seller accounts per marketplace
5. **Hybrid AI** - Local (Ollama) + Cloud (Gemini) models with budget management

### Module Structure
```
dropshipping/
├── suppliers/         # Fetcher/Parser implementations (inherit from BaseFetcher)
├── sourcing/          # Sales analysis, competitor monitoring, keyword research  
├── transformers/      # Standardize to common Product format
├── storage/           # Supabase database handler
├── ai_processors/     # Product enhancement (names, descriptions, images)
├── uploader/          # Marketplace integrations (API and Excel)
├── orders/            # Order management, shipping tracking, inventory sync
├── models/            # Data models (product, order, sourcing)
├── domain/            # Domain logic (category, pricing, validator)
├── scheduler/         # APScheduler/Cron for automation
├── mcp/              # Model Context Protocol tools
├── db/               # Database schemas and seeds (16 tables)
└── tests/            # Pytest test suites (138 tests)
```

### Key Components

#### AI Processing Pipeline
- **ModelRouter**: Selects AI model based on task complexity and budget ($50/month default)
- **ProductEnhancer**: Optimizes product names, generates descriptions, extracts SEO keywords
- **ImageProcessor**: Generates captions, removes backgrounds, adds watermarks
- **AIProcessingPipeline**: Orchestrates all AI processors

#### Marketplace Uploaders
- **CoupangUploader**: WING OpenAPI with HMAC-SHA256 authentication
- **ElevenstUploader**: XML format with OAuth authentication
- **SmartstoreUploader**: Commerce API v2 with OAuth 2.0
- **GmarketExcelUploader**: ESM Plus Excel format with pandas/openpyxl

#### Supplier Integrations
1. **Domeme/Domeggook**: REST API with XML format (implemented)
2. **Ownerclan**: GraphQL API with JWT authentication
3. **Zentrade**: Bulk XML download (~20MB)
4. **Excel**: Generic Excel file support

### Database Design
- **Platform**: Supabase (PostgreSQL)
- **Schema**: `db/schema.sql` - 16 tables implemented
- **Seed Data**: `db/seed_data.sql` - Initial data
- **Migration**: `db/migrate.py` - Migration tool

## Key Implementation Notes

- All supplier fetchers inherit from `BaseFetcher` abstract class
- All marketplace uploaders inherit from `BaseUploader` abstract class
- All AI processors inherit from `BaseAIProcessor` abstract class
- Use `StandardProduct` format for data interchange between modules
- Implement retry logic with exponential backoff for API calls
- Store all raw responses in JSONB for debugging and reprocessing
- Use `asyncio` for all async operations (avoid `pytest-asyncio` markers)
- Logging with `loguru` throughout the codebase