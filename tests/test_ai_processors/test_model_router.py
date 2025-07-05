"""
모델 라우터 테스트
"""

import pytest
from decimal import Decimal

from dropshipping.ai_processors.model_router import (
    ModelRouter,
    TaskType,
    TaskConfig,
    ModelProvider,
    ModelConfig,
)


class TestModelRouter:
    """모델 라우터 테스트"""
    
    @pytest.fixture
    def router(self):
        """테스트용 라우터"""
        return ModelRouter(monthly_budget=Decimal("10.00"))
    
    def test_init(self, router):
        """초기화 테스트"""
        assert router.monthly_budget == Decimal("10.00")
        assert router.current_usage == Decimal("0.00")
        assert len(router.models) > 0
        assert len(router.task_model_mapping) > 0
    
    def test_select_model_for_simple_task(self, router):
        """간단한 작업 모델 선택"""
        config = TaskConfig(
            task_type=TaskType.PRODUCT_NAME_ENHANCE,
            complexity="low",
            expected_tokens=100
        )
        
        model = router.select_model(config)
        assert model is not None
        assert model.model_name == "gemma:3b"
        assert model.cost_per_1k_tokens == 0  # 무료 모델
    
    def test_select_model_for_vision_task(self, router):
        """비전 작업 모델 선택"""
        config = TaskConfig(
            task_type=TaskType.BACKGROUND_REMOVE,
            complexity="high",
            expected_tokens=500,
            requires_vision=True
        )
        
        model = router.select_model(config)
        assert model is not None
        assert model.supports_vision is True
        assert model.provider == ModelProvider.GEMINI
    
    def test_select_model_by_complexity(self, router):
        """복잡도별 모델 선택"""
        # 낮은 복잡도
        config_low = TaskConfig(
            task_type=TaskType.HTML_TO_TEXT,
            complexity="low",
            expected_tokens=200
        )
        model_low = router.select_model(config_low)
        assert model_low.model_name in ["gemma:3b", "gemini-2.5-flash-mini"]
        
        # 높은 복잡도
        config_high = TaskConfig(
            task_type=TaskType.DESCRIPTION_GENERATE,
            complexity="high",
            expected_tokens=1000
        )
        model_high = router.select_model(config_high)
        assert model_high.model_name in ["qwen:14b", "deepseek-r1:7b", "gemini-2.5-flash"]
    
    def test_budget_check(self, router):
        """예산 체크 테스트"""
        # 예산 내
        config = TaskConfig(
            task_type=TaskType.SEO_KEYWORDS,
            expected_tokens=1000
        )
        
        model = router.select_model(config)
        assert model is not None
        
        # 사용량 기록
        router.record_usage("gemini-flash-mini", 10000)  # $0.001
        assert router.current_usage == Decimal("0.001")
        
        # 예산 초과 시뮬레이션
        router.current_usage = Decimal("9.998")  # $10 예산에서 $0.002 남음
        
        # 높은 비용 작업
        expensive_config = TaskConfig(
            task_type=TaskType.PRICE_ANALYSIS,
            expected_tokens=10000  # 예산 초과
        )
        
        model = router.select_model(expensive_config)
        # 무료 모델로 폴백되어야 함
        assert model is not None
        assert model.cost_per_1k_tokens == 0
    
    def test_fallback_to_free_model(self, router):
        """무료 모델 폴백 테스트"""
        # 예산 소진
        router.current_usage = router.monthly_budget
        
        config = TaskConfig(
            task_type=TaskType.DESCRIPTION_GENERATE,
            expected_tokens=1000
        )
        
        model = router.select_model(config)
        assert model is not None
        assert model.cost_per_1k_tokens == 0
        assert model.provider == ModelProvider.OLLAMA
    
    def test_estimate_cost(self, router):
        """비용 추정 테스트"""
        model = router.models["gemini-flash"]
        cost = router._estimate_cost(model, 1000)
        assert cost == Decimal("0.0003")  # 1000 tokens * $0.0003/1k
        
        # 무료 모델
        free_model = router.models["gemma-3b"]
        free_cost = router._estimate_cost(free_model, 10000)
        assert free_cost == 0
    
    def test_record_usage(self, router):
        """사용량 기록 테스트"""
        # 정상 기록
        router.record_usage("gemini-flash-mini", 5000)
        assert router.current_usage == Decimal("0.0005")
        
        # 알 수 없는 모델
        router.record_usage("unknown-model", 1000)
        # 사용량 변화 없음
        assert router.current_usage == Decimal("0.0005")
    
    def test_get_usage_report(self, router):
        """사용량 리포트 테스트"""
        router.record_usage("gemini-flash", 10000)  # $0.003
        
        report = router.get_usage_report()
        assert report["monthly_budget"] == 10.0
        assert report["current_usage"] == 0.003
        assert report["remaining_budget"] == 9.997
        assert 0 < report["usage_percentage"] < 1
    
    def test_reset_monthly_usage(self, router):
        """월간 사용량 초기화 테스트"""
        router.record_usage("gemini-flash", 10000)
        assert router.current_usage > 0
        
        router.reset_monthly_usage()
        assert router.current_usage == 0
    
    def test_task_config_validation(self):
        """작업 설정 검증"""
        # 정상 설정
        config = TaskConfig(
            task_type=TaskType.PRODUCT_NAME_ENHANCE,
            complexity="medium",
            expected_tokens=500
        )
        assert config.task_type == "product_name_enhance"
        assert config.complexity == "medium"
        
        # 잘못된 복잡도
        with pytest.raises(ValueError):
            TaskConfig(
                task_type=TaskType.PRODUCT_NAME_ENHANCE,
                complexity="very_high"  # 허용되지 않는 값
            )