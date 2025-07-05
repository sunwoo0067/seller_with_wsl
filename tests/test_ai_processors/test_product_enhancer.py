

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from decimal import Decimal

from dropshipping.ai_processors.product_enhancer import ProductEnhancer
from dropshipping.ai_processors.model_router import ModelRouter, TaskConfig, TaskType
from dropshipping.models.product import StandardProduct, ProductOption, OptionType


class TestProductEnhancer:
    """ProductEnhancer 테스트"""
    
    @pytest.fixture
    def mock_router(self):
        """Mock 모델 라우터"""
        router = Mock(spec=ModelRouter)
        router.select_model.return_value = Mock(
            model_name="test-model",
            provider="ollama",
            max_tokens=1000,
            temperature=0.7
        )
        router.record_usage = Mock()
        return router
    
    @pytest.fixture
    def enhancer(self, mock_router):
        """테스트용 향상기"""
        return ProductEnhancer(model_router=mock_router)
    
    @pytest.fixture
    def sample_product(self):
        """테스트용 상품"""
        return StandardProduct(
            id="test-1",
            supplier_id="test",
            supplier_product_id="TEST001",
            name="[특가] 테스트 상품명 ★★★ 무료배송!!!",
            brand="TestBrand",
            category_name="의류",
            price=Decimal("29900"),
            cost=Decimal("20000"),
            stock=100,
            options=[
                ProductOption(
                    name="색상",
                    type=OptionType.SELECT,
                    values=["블랙", "화이트", "그레이"]
                ),
                ProductOption(
                    name="사이즈",
                    type=OptionType.SELECT,
                    values=["S", "M", "L", "XL"]
                )
            ]
        )
    
    def test_init(self, enhancer):
        """초기화 테스트"""
        assert enhancer.model_router is not None
        assert enhancer.default_task_config is not None
        assert len(enhancer.banned_keywords) > 0
    
    def test_validate_input(self, enhancer, sample_product):
        """입력 검증 테스트"""
        # StandardProduct
        assert enhancer.validate_input(sample_product) is True
        
        # dict
        assert enhancer.validate_input({"name": "test"}) is True
        assert enhancer.validate_input({"no_name": "test"}) is False
        
        # 잘못된 타입
        assert enhancer.validate_input("string") is False
        assert enhancer.validate_input(123) is False
    
    def test_clean_product_name(self, enhancer):
        """상품명 정제 테스트"""
        # 특수문자 정리
        name = "테스트★★★★상품!!!!!!"
        cleaned = enhancer._clean_product_name(name)
        assert "★★★★" not in cleaned
        assert "!!!!" not in cleaned
        
        # 대괄호 내용 제거
        name = "[무료배송] 테스트 [특가] 상품 [당일발송]"
        cleaned = enhancer._clean_product_name(name)
        assert "[무료배송]" not in cleaned
        assert "[특가]" not in cleaned
        assert "테스트" in cleaned
        assert "상품" in cleaned
        
        # 공백 정리
        name = "테스트    상품     이름"
        cleaned = enhancer._clean_product_name(name)
        assert cleaned == "테스트 상품 이름"
    
    def test_validate_enhanced_name(self, enhancer):
        """향상된 상품명 검증 테스트"""
        # 정상
        assert enhancer._validate_enhanced_name("테스트 상품명 브랜드 모델") is True
        
        # 너무 짧음
        assert enhancer._validate_enhanced_name("테스트") is False
        
        # 너무 김
        assert enhancer._validate_enhanced_name("a" * 61) is False
        
        # 금지 키워드
        assert enhancer._validate_enhanced_name("최고의 테스트 상품") is False
        assert enhancer._validate_enhanced_name("특가 세일 상품") is False
    
    @pytest.mark.asyncio
    async def test_enhance_product_name(self, enhancer, sample_product):
        """상품명 향상 테스트"""
        # Mock 설정
        with patch.object(enhancer, '_execute_with_model') as mock_execute:
            mock_execute.return_value = {
                "content": "TestBrand 테스트 상품 의류",
                "usage": {"total_tokens": 50}
            }
            
            result = await enhancer._enhance_product_name(
                sample_product,
                TaskConfig(task_type=TaskType.PRODUCT_NAME_ENHANCE)
            )
            
            assert result == "TestBrand 테스트 상품 의류"
            assert mock_execute.called
    
    def test_prepare_name_prompt(self, enhancer, sample_product):
        """상품명 프롬프트 테스트"""
        prompt = enhancer._prepare_name_prompt(sample_product)
        assert sample_product.name in prompt
        assert sample_product.brand in prompt
        assert sample_product.category_name in prompt
    
    def test_get_price_range(self, enhancer):
        """가격대 문자열 테스트"""
        assert enhancer._get_price_range(5000) == "1만원 이하"
        assert enhancer._get_price_range(25000) == "1-3만원"
        assert enhancer._get_price_range(45000) == "3-5만원"
        assert enhancer._get_price_range(80000) == "5-10만원"
        assert enhancer._get_price_range(200000) == "10-30만원"
        assert enhancer._get_price_range(500000) == "30만원 이상"
    
    def test_format_description_html(self, enhancer):
        """HTML 포맷팅 테스트"""
        text = """주요 특징:
- 고품질 소재
- 편안한 착용감
- 다양한 색상

세부 사항
최고급 원단을 사용하여 제작되었습니다."""
        
        html = enhancer._format_description_html(text)
        assert "<h4>주요 특징:</h4>" in html
        assert "<li>고품질 소재</li>" in html
        assert "<p>최고급 원단을 사용하여 제작되었습니다.</p>" in html
        assert "<ul>" in html and "</ul>" in html
    
    def test_clean_keyword(self, enhancer):
        """키워드 정제 테스트"""
        assert enhancer._clean_keyword("테스트@#$키워드") == "테스트 키워드"
        assert enhancer._clean_keyword("  공백   많은   키워드  ") == "공백 많은 키워드"
        assert enhancer._clean_keyword("정상키워드") == "정상키워드"
    
    def test_generate_basic_keywords(self, enhancer, sample_product):
        """기본 키워드 생성 테스트"""
        keywords = enhancer._generate_basic_keywords(sample_product)
        
        assert sample_product.brand in keywords
        assert sample_product.category_name in keywords
        assert f"{sample_product.brand} {sample_product.category_name}" in keywords
        assert "1-3만원" in keywords  # 가격대
    
    @pytest.mark.asyncio
    async def test_process_all(self, enhancer, sample_product):
        """전체 처리 테스트"""
        # Mock 설정
        with patch.object(enhancer, '_enhance_product_name') as mock_name, \
             patch.object(enhancer, '_generate_description') as mock_desc, \
             patch.object(enhancer, '_extract_seo_keywords') as mock_seo:
            
            mock_name.return_value = "향상된 상품명"
            mock_desc.return_value = "<p>생성된 설명</p>"
            mock_seo.return_value = ["키워드1", "키워드2"]
            
            result = await enhancer.process(sample_product, enhance_type="all")
            
            assert result["product_id"] == sample_product.id
            assert result["original_name"] == sample_product.name
            assert result["enhancements"]["enhanced_name"] == "향상된 상품명"
            assert result["enhancements"]["generated_description"] == "<p>생성된 설명</p>"
            assert result["enhancements"]["seo_keywords"] == ["키워드1", "키워드2"]
            assert "processed_at" in result
            
            # 통계 확인
            assert enhancer.stats["processed"] == 1
    
    @pytest.mark.asyncio
    async def test_process_name_only(self, enhancer, sample_product):
        """이름만 처리 테스트"""
        with patch.object(enhancer, '_enhance_product_name') as mock_name:
            mock_name.return_value = "향상된 상품명"
            
            result = await enhancer.process(
                sample_product, 
                enhance_type="name"
            )
            
            assert "enhanced_name" in result["enhancements"]
            assert "generated_description" not in result["enhancements"]
            assert "seo_keywords" not in result["enhancements"]
    
    @pytest.mark.asyncio
    async def test_process_with_dict_input(self, enhancer):
        """딕셔너리 입력 처리 테스트"""
        product_dict = {
            "id": "test-1",
            "supplier_id": "test",
            "supplier_product_id": "TEST001",
            "name": "테스트 상품",
            "price": 10000,
            "cost": 8000,
            "stock": 10
        }
        
        with patch.object(enhancer, '_enhance_product_name') as mock_name:
            mock_name.return_value = "향상된 테스트 상품"
            
            result = await enhancer.process(
                product_dict,
                enhance_type="name"
            )
            
            assert result["product_id"] == "test-1"
            assert result["original_name"] == "테스트 상품"

    @pytest.mark.asyncio
    async def test_generate_description(self, enhancer, sample_product):
        """설명 생성 테스트"""
        with patch.object(enhancer, '_execute_with_model') as mock_execute:
            mock_execute.return_value = {
                "content": "<p>이것은 생성된 설명입니다.</p>",
                "usage": {"total_tokens": 300}
            }
            
            result = await enhancer._generate_description(
                sample_product,
                TaskConfig(task_type=TaskType.DESCRIPTION_GENERATE)
            )
            
            assert "<p>이것은 생성된 설명입니다.</p>" in result
            assert mock_execute.called

    @pytest.mark.asyncio
    async def test_extract_seo_keywords(self, enhancer, sample_product):
        """SEO 키워드 추출 테스트"""
        with patch.object(enhancer, '_execute_with_model') as mock_execute:
            mock_execute.return_value = {
                "content": "[\"키워드1\", \"키워드2\"]",
                "usage": {"total_tokens": 50}
            }
            
            result = await enhancer._extract_seo_keywords(
                sample_product,
                TaskConfig(task_type=TaskType.SEO_KEYWORDS)
            )
            
            assert "키워드1" in result
            assert "키워드2" in result
            assert mock_execute.called
