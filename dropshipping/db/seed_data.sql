-- Dropshipping Automation System Seed Data
-- 초기 설정 데이터

-- =====================================
-- 공급사 데이터
-- =====================================

INSERT INTO suppliers (code, name, api_type, api_config, is_active) VALUES
('domeme', '도매매/도매꾹', 'rest', 
 '{"base_url": "https://api.domeggook.com/open/v4.1/search/searchProductList.do", "auth_type": "api_key"}', 
 true),
('ownerclan', '오너클랜', 'graphql', 
 '{"base_url": "https://api.ownerclan.com/graphql", "auth_type": "jwt"}', 
 true),
('zentrade', '젠트레이드', 'xml', 
 '{"download_url": "https://zentrade.co.kr/api/products.xml", "auth_type": "api_key"}', 
 true),
('excel_custom', '엑셀 업로드', 'excel', 
 '{"file_format": "xlsx", "encoding": "utf-8"}', 
 true);

-- =====================================
-- 마켓플레이스 데이터
-- =====================================

INSERT INTO marketplaces (code, name, type, api_config, fee_rate, is_active) VALUES
('coupang', '쿠팡', 'api', 
 '{"base_url": "https://api-gateway.coupang.com", "version": "v2"}', 
 0.108, true),
('11st', '11번가', 'api', 
 '{"base_url": "https://api.11st.co.kr/rest", "version": "v2"}', 
 0.12, true),
('smartstore', '네이버 스마트스토어', 'api', 
 '{"base_url": "https://api.commerce.naver.com", "version": "v1"}', 
 0.058, true),
('gmarket', 'G마켓', 'excel', 
 '{"template_type": "esmplus", "encoding": "euc-kr"}', 
 0.13, true),
('auction', '옥션', 'excel', 
 '{"template_type": "esmplus", "encoding": "euc-kr"}', 
 0.13, true);

-- =====================================
-- AI 모델 데이터
-- =====================================

INSERT INTO ai_models (provider, model_name, model_type, config, cost_per_1k_tokens, is_active) VALUES
-- Ollama (로컬 모델)
('ollama', 'gemma:3b', 'text', 
 '{"max_tokens": 4096, "temperature": 0.7, "local": true}', 
 0, true),
('ollama', 'deepseek-r1:7b', 'text', 
 '{"max_tokens": 8192, "temperature": 0.7, "local": true}', 
 0, true),
('ollama', 'qwen:14b', 'text', 
 '{"max_tokens": 8192, "temperature": 0.7, "local": true}', 
 0, true),

-- Google Gemini
('gemini', 'gemini-2.5-flash-mini', 'text', 
 '{"max_tokens": 8192, "temperature": 0.8}', 
 0.0001, true), -- $0.0001/1K tokens
('gemini', 'gemini-2.5-flash', 'text', 
 '{"max_tokens": 32768, "temperature": 0.8}', 
 0.0005, true), -- $0.0005/1K tokens

-- Vision 모델
('gemini', 'gemini-pro-vision', 'vision', 
 '{"max_tokens": 4096, "temperature": 0.7}', 
 0.001, true);

-- =====================================
-- 기본 가격 책정 규칙
-- =====================================

INSERT INTO pricing_rules (name, priority, conditions, pricing_method, pricing_params, additional_costs, round_to, is_active) VALUES
-- 저가 상품 규칙 (1만원 미만)
('저가 상품 규칙', 10,
 '{"max_cost": 10000}',
 'margin_rate',
 '{"margin_rate": 0.5, "min_margin_amount": 2000}',
 '{"platform_fee_rate": 0.1, "payment_fee_rate": 0.03, "packaging_cost": 1000, "handling_cost": 500}',
 100, true),

-- 중가 상품 규칙 (1만원 ~ 5만원)
('중가 상품 규칙', 9,
 '{"min_cost": 10000, "max_cost": 50000}',
 'margin_rate',
 '{"margin_rate": 0.3, "min_margin_amount": 3000}',
 '{"platform_fee_rate": 0.1, "payment_fee_rate": 0.03, "packaging_cost": 1000, "handling_cost": 500}',
 100, true),

-- 고가 상품 규칙 (5만원 이상)
('고가 상품 규칙', 8,
 '{"min_cost": 50000}',
 'margin_rate',
 '{"margin_rate": 0.2, "min_margin_amount": 10000}',
 '{"platform_fee_rate": 0.1, "payment_fee_rate": 0.03, "packaging_cost": 1500, "handling_cost": 1000}',
 1000, true),

-- 패션 카테고리 특별 규칙
('패션 카테고리 규칙', 15,
 '{"category_codes": ["001", "002"]}',
 'margin_rate',
 '{"margin_rate": 0.4, "min_margin_amount": 5000}',
 '{"platform_fee_rate": 0.1, "payment_fee_rate": 0.03, "packaging_cost": 1200, "handling_cost": 800}',
 900, true),

-- 기본 규칙 (fallback)
('기본 규칙', 0,
 '{}',
 'margin_rate',
 '{"margin_rate": 0.25, "min_margin_amount": 2000}',
 '{"platform_fee_rate": 0.1, "payment_fee_rate": 0.03, "packaging_cost": 1000, "handling_cost": 500}',
 100, true);

-- =====================================
-- 카테고리 매핑 예시
-- =====================================

-- 도매매 -> 쿠팡 카테고리 매핑
INSERT INTO category_mappings (supplier_id, marketplace_id, supplier_category_code, supplier_category_name, marketplace_category_code, marketplace_category_name, confidence, is_manual)
SELECT 
    s.id,
    m.id,
    mapping.supplier_code,
    mapping.supplier_name,
    mapping.marketplace_code,
    mapping.marketplace_name,
    mapping.confidence,
    mapping.is_manual
FROM suppliers s
CROSS JOIN marketplaces m
CROSS JOIN (VALUES
    ('001', '패션의류', '194176', '여성패션', 1.0, true),
    ('002', '패션잡화', '194178', '패션잡화', 1.0, true),
    ('003', '화장품/미용', '194179', '뷰티', 1.0, true),
    ('004', '디지털/가전', '194282', '가전디지털', 1.0, true),
    ('005', '가구/인테리어', '194183', '생활/가구', 0.9, false),
    ('006', '식품', '194195', '식품', 1.0, true),
    ('007', '스포츠/레저', '194190', '스포츠/레저', 1.0, true),
    ('008', '생활용품', '194183', '생활/가구', 0.8, false),
    ('009', '출산/육아', '194187', '출산/유아동', 1.0, true),
    ('010', '반려동물', '194193', '반려동물', 1.0, true)
) AS mapping(supplier_code, supplier_name, marketplace_code, marketplace_name, confidence, is_manual)
WHERE s.code = 'domeme' AND m.code = 'coupang';

-- =====================================
-- 테스트용 판매자 계정 (실제 사용시 삭제)
-- =====================================

INSERT INTO seller_accounts (marketplace_id, account_name, credentials, settings, is_active)
SELECT 
    m.id,
    'Test Account - ' || m.name,
    '{"api_key": "test_key_' || m.code || '", "secret": "test_secret_' || m.code || '"}',
    '{"auto_price_sync": true, "inventory_sync": true}',
    true
FROM marketplaces m
WHERE m.type = 'api';