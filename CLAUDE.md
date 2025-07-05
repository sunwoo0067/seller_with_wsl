# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

한국어로 대답해줘.

# Gemini CLI 도구 사용

대용량 코드 구조나 전체 파일 분석이 필요하면 다음처럼 Gemini CLI 사용:

```tool:gemini
gemini -p "@src/ 전체 코드 구조를 요약해줘"
gemini -p "@src/main.py 이 파일이 하는 역할을 설명해줘"
```

## Project Overview

This is a **Dropshipping Automation System** that automates the entire workflow from supplier product collection to marketplace listing and order management. The system is built with Python 3.11, uses Supabase as database, and includes comprehensive test coverage.

## Commands

```bash
# Environment Setup
source activate.sh             # 가상환경 활성화 (Linux/Mac)
pip install -r requirements.txt # 의존성 설치
cp .env.example .env           # 환경 변수 설정
python db/migrate.py           # 데이터베이스 마이그레이션

# Development
python -m dropshipping.main    # CLI 인터페이스 실행
python -m dropshipping.main collect --supplier domeme  # 특정 공급사 수집
python -m dropshipping.main upload --marketplace coupang  # 특정 마켓 업로드

# Testing
pytest                          # 전체 테스트 실행
pytest -v                       # 상세 테스트 실행  
pytest --cov=dropshipping      # 커버리지 포함 테스트
pytest tests/test_specific.py  # 특정 테스트 파일 실행
pytest -k "test_name"          # 특정 테스트 함수 실행
pytest -s                      # print 출력 포함 테스트

# Code Quality
black dropshipping tests        # 코드 포맷팅
ruff check dropshipping tests   # 린팅
mypy dropshipping              # 타입 검사
ruff check --fix               # 자동 수정 가능한 린트 오류 수정

# Database
python db/migrate.py           # 스키마 마이그레이션
python db/seed_data.py         # 시드 데이터 로드
```

## Architecture

### Core Design Principles
1. **Abstract Base Classes** - All major components inherit from Base* classes for consistency
2. **Dependency Injection** - Configuration injected through constructors
3. **Data Preservation** - Raw responses stored in JSONB for debugging/reprocessing
4. **Incremental Processing** - Process newest items first, resume-able operations
5. **Error Resilience** - Retry logic with exponential backoff, graceful degradation

### Module Structure
```
dropshipping/
├── suppliers/         # Product collection (BaseFetcher implementations)
│   ├── domeme/       # Domeme/Domeggook API (XML)
│   ├── ownerclan/    # Ownerclan GraphQL API  
│   ├── zentrade/     # Zentrade bulk XML
│   └── excel/        # Generic Excel support
├── transformers/      # Convert raw data to StandardProduct format
├── storage/           # Data persistence layer
│   ├── supabase_storage.py  # PostgreSQL via Supabase
│   └── json_storage.py      # Local JSON backup
├── ai_processors/     # AI enhancement pipeline
│   ├── product_enhancer.py  # Name/description optimization
│   ├── image_processor.py   # Image captions, background removal
│   └── model_router.py      # Model selection by budget/complexity
├── uploader/          # Marketplace integrations (BaseUploader)
│   ├── coupang.py    # WING OpenAPI
│   ├── elevenst.py   # XML format with OAuth
│   ├── smartstore.py # Commerce API v2
│   └── gmarket_excel.py # ESM Plus Excel format
├── orders/            # Order lifecycle management
├── sourcing/          # Market analysis tools
├── scheduler/         # Task automation
├── monitoring/        # System health & alerts
├── models/            # Pydantic data models
├── domain/            # Business logic (pricing, validation)
├── mcp/              # Model Context Protocol tools
├── db/               # Database management
│   ├── schema.sql    # PostgreSQL schema (16 tables)
│   ├── seed_data.sql # Initial data
│   └── migrate.py    # Migration tool
└── tests/            # Comprehensive test suite
```

### Data Flow
1. **Collection**: Fetcher → Raw JSON (products_raw table)
2. **Transformation**: Transformer → StandardProduct format
3. **Enhancement**: AI Processors → Enhanced product data
4. **Upload**: Uploader → Marketplace-specific format
5. **Monitoring**: Order sync → Inventory updates → Notifications

### Key Classes and Interfaces
- `BaseFetcher`: Abstract class for all supplier integrations
- `BaseTransformer`: Convert supplier data to standard format
- `BaseUploader`: Abstract class for marketplace integrations
- `BaseAIProcessor`: AI processing pipeline interface
- `StandardProduct`: Common data model for all products
- `ModelRouter`: Selects optimal AI model based on task/budget

## Common Tasks

### Adding a New Supplier
1. Create `dropshipping/suppliers/new_supplier/`
2. Implement `fetcher.py` inheriting from `BaseFetcher`
3. Implement `transformer.py` inheriting from `BaseTransformer`
4. Add tests in `tests/suppliers/test_new_supplier.py`
5. Register in `config.py` SUPPLIERS list

### Adding a New Marketplace
1. Create `dropshipping/uploader/new_marketplace.py`
2. Inherit from `BaseUploader`
3. Implement required methods: `upload_product()`, `check_upload_status()`
4. Add marketplace config to `.env`
5. Add tests in `tests/uploader/test_new_marketplace.py`

### Debugging Tips
- Check logs in `logs/` directory (loguru rotating files)
- Raw API responses stored in `products_raw.raw_json` column
- Use `pytest -s` to see print statements during tests
- Set `LOG_LEVEL=DEBUG` in `.env` for verbose logging
- Use breakpoints: `import pdb; pdb.set_trace()`

## Environment Variables (.env)
```bash
# Database
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your-anon-key

# AI Models
OPENAI_API_KEY=sk-xxx
GEMINI_API_KEY=xxx
OLLAMA_HOST=http://localhost:11434

# Suppliers
DOMEME_API_KEY=xxx
OWNERCLAN_TOKEN=xxx

# Marketplaces
COUPANG_ACCESS_KEY=xxx
COUPANG_SECRET_KEY=xxx
ELEVENST_API_KEY=xxx

# Monitoring
SLACK_WEBHOOK_URL=https://hooks.slack.com/xxx
```

## Testing Strategy
- **Unit Tests**: Mock external dependencies (API calls, DB)
- **Integration Tests**: Use test database, real API calls with test accounts
- **Fixtures**: Common test data in `conftest.py`
- **Test Isolation**: Each test runs in transaction, rolled back after
- **Coverage Goal**: Maintain >80% coverage

## Current Status
- ✅ Core architecture implemented
- ✅ Domeme supplier integration complete
- ✅ Supabase storage layer complete
- ✅ AI processing pipeline complete
- ✅ Coupang marketplace integration complete
- ✅ 138 tests passing with 85% coverage
- 🚧 Ownerclan, Zentrade suppliers in progress
- 🚧 Order management module in progress
- 📋 Scheduler and monitoring planned

## Troubleshooting
- **Import Errors**: Run from project root, check `PYTHONPATH`
- **Database Errors**: Verify Supabase connection, run migrations
- **API Rate Limits**: Implement exponential backoff, use batch operations
- **Memory Issues**: Process in chunks, use generators for large datasets
- **Async Errors**: Use `asyncio.run()` for standalone scripts