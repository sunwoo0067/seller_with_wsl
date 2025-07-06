-- 초기 공급사 데이터 시드
-- PRD v1.0 - Phase 1 산출물

INSERT INTO suppliers (code, name, api_type, api_config)
VALUES
    ('domeme', '도매매', 'rest', '{"base_url": "https://api.domeme.com/v4/"}'),
    ('ownerclan', '오너클랜', 'rest', '{"base_url": "https://api.ownerclan.com/v1/"}'),
    ('zentrade', '젠트레이드', 'xml', '{"ftp_url": "ftp://zentrade.co.kr/products.xml"}'),
    ('excel_generic', '엑셀(일반)', 'excel', '{}')
ON CONFLICT (code) DO NOTHING;
