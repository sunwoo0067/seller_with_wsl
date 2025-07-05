-- Dropshipping Automation System Database Schema
-- Supabase (PostgreSQL) 기반
-- 생성일: 2024-12-16

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================
-- 1. 메타데이터 테이블
-- =====================================

-- 공급사 정보
CREATE TABLE suppliers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    api_type VARCHAR(20) NOT NULL CHECK (api_type IN ('rest', 'graphql', 'xml', 'excel')),
    api_config JSONB,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 마켓플레이스 정보
CREATE TABLE marketplaces (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('api', 'excel')),
    api_config JSONB,
    fee_rate DECIMAL(5,4) DEFAULT 0.1,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 판매자 계정 (마켓플레이스별 다중 계정)
CREATE TABLE seller_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    marketplace_id UUID NOT NULL REFERENCES marketplaces(id),
    account_name VARCHAR(100) NOT NULL,
    credentials JSONB, -- 암호화된 인증 정보
    settings JSONB,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- AI 모델 정보
CREATE TABLE ai_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider VARCHAR(50) NOT NULL, -- 'ollama', 'gemini', 'openai'
    model_name VARCHAR(100) NOT NULL,
    model_type VARCHAR(50) NOT NULL, -- 'text', 'vision', 'embedding'
    config JSONB,
    cost_per_1k_tokens DECIMAL(10,6),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================
-- 2. 상품 관련 테이블
-- =====================================

-- 원본 상품 데이터 (공급사별 원본 보존)
CREATE TABLE products_raw (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    supplier_id UUID NOT NULL REFERENCES suppliers(id),
    supplier_product_id VARCHAR(100) NOT NULL,
    raw_json JSONB NOT NULL, -- 원본 데이터 그대로 저장
    data_hash VARCHAR(64) NOT NULL, -- SHA256 중복 체크용
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(supplier_id, data_hash)
);

-- 처리된 표준 상품 정보
CREATE TABLE products_processed (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    raw_id UUID REFERENCES products_raw(id),
    supplier_id UUID NOT NULL REFERENCES suppliers(id),
    supplier_product_id VARCHAR(100) NOT NULL,
    
    -- 기본 정보
    name VARCHAR(500) NOT NULL,
    brand VARCHAR(200),
    manufacturer VARCHAR(200),
    origin VARCHAR(100),
    
    -- 가격 정보
    cost DECIMAL(12,2) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    list_price DECIMAL(12,2),
    
    -- 재고 정보
    stock INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    
    -- 카테고리
    category_code VARCHAR(50),
    category_name VARCHAR(200),
    category_path TEXT[],
    
    -- 이미지
    images JSONB, -- [{url, is_main, order}]
    
    -- 옵션
    options JSONB, -- [{name, type, values, required}]
    
    -- 추가 속성
    attributes JSONB,
    
    -- 메타데이터
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(supplier_id, supplier_product_id)
);

-- 상품 변형 (옵션 조합)
CREATE TABLE product_variants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products_processed(id) ON DELETE CASCADE,
    sku VARCHAR(200) UNIQUE NOT NULL,
    option_values JSONB NOT NULL, -- {"색상": "블랙", "사이즈": "L"}
    additional_cost DECIMAL(10,2) DEFAULT 0,
    stock INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- AI 처리된 상품 정보
CREATE TABLE products_ai_enhanced (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products_processed(id),
    ai_model_id UUID REFERENCES ai_models(id),
    
    -- AI 생성 콘텐츠
    enhanced_name VARCHAR(500),
    enhanced_description TEXT,
    seo_keywords TEXT[],
    bullet_points TEXT[],
    
    -- 이미지 처리
    processed_images JSONB, -- [{original_url, processed_url, type}]
    
    -- 처리 정보
    processing_time_ms INTEGER,
    tokens_used INTEGER,
    processing_cost DECIMAL(10,6),
    
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================
-- 3. 마켓플레이스 관련 테이블
-- =====================================

-- 마켓플레이스 상품 목록
CREATE TABLE marketplace_listings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products_processed(id),
    marketplace_id UUID NOT NULL REFERENCES marketplaces(id),
    account_id UUID NOT NULL REFERENCES seller_accounts(id),
    
    -- 마켓 정보
    marketplace_product_id VARCHAR(100),
    marketplace_url TEXT,
    
    -- 가격 정보
    listing_price DECIMAL(12,2) NOT NULL,
    shipping_fee DECIMAL(10,2) DEFAULT 0,
    
    -- 상태
    status VARCHAR(20) DEFAULT 'pending', -- pending, active, paused, soldout, error
    
    -- 매핑 정보
    marketplace_category_id VARCHAR(100),
    marketplace_category_name VARCHAR(200),
    
    -- 업로드 정보
    uploaded_at TIMESTAMPTZ,
    last_synced_at TIMESTAMPTZ,
    sync_error TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(product_id, marketplace_id, account_id)
);

-- =====================================
-- 4. 규칙 및 설정 테이블
-- =====================================

-- 카테고리 매핑 규칙
CREATE TABLE category_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    supplier_id UUID REFERENCES suppliers(id),
    marketplace_id UUID NOT NULL REFERENCES marketplaces(id),
    
    supplier_category_code VARCHAR(100),
    supplier_category_name VARCHAR(200),
    marketplace_category_code VARCHAR(100) NOT NULL,
    marketplace_category_name VARCHAR(200),
    
    confidence DECIMAL(3,2) DEFAULT 1.0,
    is_manual BOOLEAN DEFAULT false,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 가격 책정 규칙
CREATE TABLE pricing_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(200) NOT NULL,
    priority INTEGER DEFAULT 0,
    
    -- 조건
    conditions JSONB NOT NULL, -- {min_cost, max_cost, category_codes, supplier_ids}
    
    -- 가격 책정
    pricing_method VARCHAR(20) NOT NULL, -- margin_rate, fixed_margin, competitive
    pricing_params JSONB NOT NULL, -- {margin_rate, fixed_margin, min_margin, max_margin}
    
    -- 추가 비용
    additional_costs JSONB, -- {platform_fee_rate, payment_fee_rate, packaging_cost}
    
    -- 가격 조정
    round_to INTEGER DEFAULT 100,
    price_ending INTEGER,
    
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================
-- 5. 주문 및 재고 관리
-- =====================================

-- 주문 정보
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    marketplace_id UUID NOT NULL REFERENCES marketplaces(id),
    account_id UUID NOT NULL REFERENCES seller_accounts(id),
    listing_id UUID REFERENCES marketplace_listings(id),
    
    -- 주문 정보
    marketplace_order_id VARCHAR(100) NOT NULL,
    order_date TIMESTAMPTZ NOT NULL,
    
    -- 상품 정보
    product_name VARCHAR(500),
    options JSONB,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    
    -- 고객 정보
    buyer_name VARCHAR(100),
    buyer_phone VARCHAR(50),
    buyer_email VARCHAR(200),
    
    -- 배송 정보
    shipping_address JSONB,
    shipping_method VARCHAR(50),
    tracking_number VARCHAR(100),
    
    -- 상태
    status VARCHAR(20) DEFAULT 'pending',
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(marketplace_id, marketplace_order_id)
);

-- 재고 동기화 로그
CREATE TABLE inventory_sync_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID REFERENCES products_processed(id),
    variant_id UUID REFERENCES product_variants(id),
    
    -- 재고 변동
    previous_stock INTEGER,
    new_stock INTEGER,
    change_amount INTEGER,
    change_reason VARCHAR(50), -- 'order', 'manual', 'supplier_update'
    
    -- 관련 정보
    order_id UUID REFERENCES orders(id),
    
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================
-- 6. 소싱 인텔리전스 테이블
-- =====================================

-- 키워드 연구
CREATE TABLE keyword_research (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    marketplace_id UUID NOT NULL REFERENCES marketplaces(id),
    
    keyword VARCHAR(200) NOT NULL,
    category VARCHAR(200),
    
    -- 검색 데이터
    search_volume INTEGER,
    competition_level VARCHAR(20), -- low, medium, high
    avg_price DECIMAL(12,2),
    product_count INTEGER,
    
    -- 트렌드
    trend_direction VARCHAR(20), -- up, down, stable
    trend_percentage DECIMAL(5,2),
    
    researched_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 경쟁사 모니터링
CREATE TABLE competitor_products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    marketplace_id UUID NOT NULL REFERENCES marketplaces(id),
    
    -- 경쟁 상품 정보
    competitor_name VARCHAR(200),
    product_url TEXT,
    product_name VARCHAR(500),
    
    -- 가격 정보
    price DECIMAL(12,2),
    shipping_fee DECIMAL(10,2),
    
    -- 판매 정보
    sales_count INTEGER,
    review_count INTEGER,
    review_rating DECIMAL(2,1),
    
    -- 분석
    our_product_id UUID REFERENCES products_processed(id),
    price_difference DECIMAL(12,2),
    
    monitored_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================
-- 7. 시스템 로그 및 모니터링
-- =====================================

-- 파이프라인 실행 로그
CREATE TABLE pipeline_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pipeline_type VARCHAR(50) NOT NULL, -- 'fetch', 'process', 'ai_enhance', 'upload'
    
    -- 실행 정보
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    
    -- 대상
    target_type VARCHAR(50), -- 'supplier', 'product', 'marketplace'
    target_id UUID,
    
    -- 결과
    status VARCHAR(20), -- 'running', 'success', 'failed'
    records_processed INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    error_message TEXT,
    
    -- 상세 로그
    details JSONB,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================
-- 인덱스 생성
-- =====================================

-- 성능 최적화를 위한 인덱스
CREATE INDEX idx_products_raw_supplier ON products_raw(supplier_id);
CREATE INDEX idx_products_raw_fetched ON products_raw(fetched_at DESC);
CREATE INDEX idx_products_processed_supplier ON products_processed(supplier_id);
CREATE INDEX idx_products_processed_status ON products_processed(status);
CREATE INDEX idx_marketplace_listings_product ON marketplace_listings(product_id);
CREATE INDEX idx_marketplace_listings_status ON marketplace_listings(status);
CREATE INDEX idx_orders_marketplace ON orders(marketplace_id, order_date DESC);
CREATE INDEX idx_pipeline_logs_type_status ON pipeline_logs(pipeline_type, status, started_at DESC);

-- =====================================
-- 트리거 함수
-- =====================================

-- updated_at 자동 업데이트 함수
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- updated_at 트리거 생성
CREATE TRIGGER update_suppliers_updated_at BEFORE UPDATE ON suppliers FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_marketplaces_updated_at BEFORE UPDATE ON marketplaces FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_seller_accounts_updated_at BEFORE UPDATE ON seller_accounts FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_ai_models_updated_at BEFORE UPDATE ON ai_models FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_products_processed_updated_at BEFORE UPDATE ON products_processed FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_product_variants_updated_at BEFORE UPDATE ON product_variants FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_marketplace_listings_updated_at BEFORE UPDATE ON marketplace_listings FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_category_mappings_updated_at BEFORE UPDATE ON category_mappings FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_pricing_rules_updated_at BEFORE UPDATE ON pricing_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =====================================
-- RLS (Row Level Security) 정책
-- =====================================

-- 모든 테이블에 RLS 활성화
ALTER TABLE suppliers ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketplaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE seller_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_models ENABLE ROW LEVEL SECURITY;
ALTER TABLE products_raw ENABLE ROW LEVEL SECURITY;
ALTER TABLE products_processed ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE products_ai_enhanced ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketplace_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE category_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE pricing_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_sync_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE keyword_research ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_logs ENABLE ROW LEVEL SECURITY;

-- Service role은 모든 데이터에 접근 가능
CREATE POLICY "Service role can access all data" ON suppliers FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON marketplaces FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON seller_accounts FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON ai_models FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON products_raw FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON products_processed FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON product_variants FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON products_ai_enhanced FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON marketplace_listings FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON category_mappings FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON pricing_rules FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON orders FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON inventory_sync_logs FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON keyword_research FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON competitor_products FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all data" ON pipeline_logs FOR ALL USING (auth.role() = 'service_role');