# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

한국어로 대답해줘.

## Project Overview

This is a **Dropshipping Automation System** that automates the entire workflow from supplier product collection to marketplace listing and order management. The project is currently in Phase 0 (Documentation and Planning).

## Commands

*Note: Build/test/lint commands will be defined once implementation begins. The project uses Python as the primary language.*

## Architecture

### Core Principles
1. **Modular & Extensible** - Hot-swappable suppliers, marketplaces, and AI models
2. **Preserve Original Data** - Store raw data in `products_raw.raw_json` (JSONB) without modification
3. **Incremental Processing** - Process newest to oldest, sync once daily
4. **Multi-Account Support** - Multiple seller accounts per marketplace
5. **Hybrid AI** - Local (Ollama) + Cloud (Gemini) models

### Database Design
- **Platform**: Supabase (PostgreSQL)
- **16 Tables** organized into:
  - Meta tables: suppliers, marketplaces, accounts, AI models
  - Product tables: raw, processed, listings
  - Category/pricing rules
  - Pipeline logs
  - Sourcing data

### Module Structure
```
dropshipping/
├── suppliers/         # Fetcher/Parser implementations (inherit from BaseFetcher)
├── sourcing/          # Sales analysis, competitor monitoring, keyword research
├── transformers/      # Standardize to common Product format
├── storage/           # Supabase database handler
├── ai_processors/     # Product enhancement (names, descriptions, images)
├── uploader/          # Marketplace integrations (API and Excel)
├── scheduler/         # APScheduler/Cron for automation
├── mcp/              # Model Context Protocol tools
├── db/               # Database schemas and seeds
└── tests/            # Pytest test suites
```

### AI Integration
- **Local Models** (Ollama on RTX 4070): Gemma 3n QAT, DeepSeek-R1 7B, Qwen 3 14B
- **Cloud Models**: Gemini 2.5 Flash Mini/Flash for bulk operations
- **Model Router**: Automatic selection based on task complexity and cost

### Supplier Integrations
1. **Domeme/Domeggook**: REST API with XML format
2. **Ownerclan**: GraphQL API with JWT authentication
3. **Zentrade**: Bulk XML download (~20MB)
4. **Excel**: Generic Excel file support

### Marketplace Integrations
- **API**: Coupang, 11st, SmartStore
- **Excel**: Gmarket, Auction

## Implementation Roadmap

**Current Phase**: Phase 0 - Documentation and Planning

**Next Steps**:
1. Create `db/schema.sql` with all 16 tables
2. Set up `.env.example` with required environment variables
3. Implement `storage/supabase_handler.py`
4. Create `db/seed_suppliers.sql` with initial data
5. Begin Phase 1: Implement BaseFetcher and Domeme integration

**8-Phase Implementation Plan**:
- Phase 1: Ingestion (Domeme → Supabase)
- Phase 2: Add remaining suppliers
- Phase 3: AI processing pipeline
- Phase 4: Marketplace uploaders
- Phase 5: Order management
- Phase 6: Sourcing intelligence
- Phase 7: Scheduler automation
- Phase 8: Monitoring and optimization

## Key Implementation Notes

- All supplier fetchers inherit from `BaseFetcher` abstract class
- Use `StandardProduct` format for data interchange between modules
- Implement retry logic with exponential backoff for API calls
- Store all raw responses in JSONB for debugging and reprocessing
- Use model registry for dynamic AI model selection
- Implement proper error handling and logging throughout