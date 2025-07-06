-- 기본 가격 책정 규칙 데이터 시드
-- PRD v1.0 - Phase 3 산출물

INSERT INTO pricing_rules (
    name,
    priority,
    conditions,
    pricing_method,
    pricing_params,
    round_to,
    is_active
)
VALUES
(
    '기본 마진 규칙 (원가 x 1.35 + 3,000원)',
    100, -- 낮은 우선순위 (기본값으로 사용)
    '{}', -- 모든 상품에 적용
    'margin_rate', -- 가격 계산 방식 (스키마 제약에 따름)
    '{
        "margin_rate": 0.35,
        "fixed_addition": 3000
     }', -- 마진율 35%, 고정 추가금 3000원 (애플리케이션 로직에서 활용)
    100, -- 100원 단위로 올림
    true
)
ON CONFLICT (name) DO NOTHING;
