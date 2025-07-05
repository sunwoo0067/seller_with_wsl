"""
AI 모델 라우터
작업 복잡도와 비용에 따라 적절한 AI 모델을 선택
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from decimal import Decimal

from loguru import logger
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """AI 작업 유형"""
    
    # 텍스트 처리
    PRODUCT_NAME_ENHANCE = "product_name_enhance"
    DESCRIPTION_GENERATE = "description_generate"
    SEO_KEYWORDS = "seo_keywords"
    HTML_TO_TEXT = "html_to_text"
    
    # 이미지 처리
    IMAGE_CAPTION = "image_caption"
    BACKGROUND_REMOVE = "background_remove"
    WATERMARK_ADD = "watermark_add"
    
    # 분석
    CATEGORY_SUGGEST = "category_suggest"
    PRICE_ANALYSIS = "price_analysis"
    QUALITY_SCORE = "quality_score"


class ModelProvider(str, Enum):
    """모델 제공자"""
    
    OLLAMA = "ollama"  # 로컬 모델
    GEMINI = "gemini"  # Google Gemini
    OPENAI = "openai"  # OpenAI (확장용)


@dataclass
class ModelConfig:
    """모델 설정"""
    
    provider: ModelProvider
    model_name: str
    max_tokens: int
    temperature: float
    cost_per_1k_tokens: Decimal  # 1000 토큰당 비용 (USD)
    supports_vision: bool = False
    supports_json: bool = True
    context_window: int = 8192


class TaskConfig(BaseModel):
    """작업 설정"""
    
    task_type: TaskType
    complexity: str = Field(default="low", pattern="^(low|medium|high)$")
    expected_tokens: int = Field(default=500, ge=10, le=10000)
    requires_vision: bool = False
    requires_json: bool = False
    priority: int = Field(default=5, ge=1, le=10)
    
    model_config = {"use_enum_values": True}


class ModelRouter:
    """AI 모델 라우터"""
    
    def __init__(self, monthly_budget: Decimal = Decimal("50.00")):
        """
        Args:
            monthly_budget: 월 예산 (USD)
        """
        self.monthly_budget = monthly_budget
        self.current_usage = Decimal("0.00")
        
        # 사용 가능한 모델 설정
        self.models = {
            # 로컬 모델 (Ollama)
            "gemma-3b": ModelConfig(
                provider=ModelProvider.OLLAMA,
                model_name="gemma:3b",
                max_tokens=2048,
                temperature=0.7,
                cost_per_1k_tokens=Decimal("0.00"),  # 무료
                context_window=8192
            ),
            "deepseek-r1-7b": ModelConfig(
                provider=ModelProvider.OLLAMA,
                model_name="deepseek-r1:7b",
                max_tokens=4096,
                temperature=0.7,
                cost_per_1k_tokens=Decimal("0.00"),
                context_window=16384
            ),
            "qwen-3-14b": ModelConfig(
                provider=ModelProvider.OLLAMA,
                model_name="qwen:14b",
                max_tokens=4096,
                temperature=0.7,
                cost_per_1k_tokens=Decimal("0.00"),
                context_window=32768
            ),
            
            # 클라우드 모델 (Gemini)
            "gemini-flash-mini": ModelConfig(
                provider=ModelProvider.GEMINI,
                model_name="gemini-2.5-flash-mini",
                max_tokens=8192,
                temperature=0.7,
                cost_per_1k_tokens=Decimal("0.0001"),  # $0.0001/1k tokens
                supports_vision=True,
                context_window=65536
            ),
            "gemini-flash": ModelConfig(
                provider=ModelProvider.GEMINI,
                model_name="gemini-2.5-flash",
                max_tokens=8192,
                temperature=0.7,
                cost_per_1k_tokens=Decimal("0.0003"),  # $0.0003/1k tokens
                supports_vision=True,
                context_window=131072
            ),
        }
        
        # 작업별 기본 모델 매핑
        self.task_model_mapping = {
            # 간단한 텍스트 작업 - 로컬
            TaskType.PRODUCT_NAME_ENHANCE: "gemma-3b",
            TaskType.HTML_TO_TEXT: "gemma-3b",
            TaskType.IMAGE_CAPTION: "qwen-3-14b",
            
            # 복잡한 텍스트 작업 - 고급 로컬 또는 클라우드
            TaskType.DESCRIPTION_GENERATE: "deepseek-r1-7b",
            TaskType.SEO_KEYWORDS: "gemini-flash-mini",
            TaskType.CATEGORY_SUGGEST: "qwen-3-14b",
            
            # 분석 작업 - 클라우드
            TaskType.PRICE_ANALYSIS: "gemini-flash",
            TaskType.QUALITY_SCORE: "gemini-flash-mini",
            
            # 이미지 작업 - 비전 모델 필요
            TaskType.BACKGROUND_REMOVE: "gemini-flash",
            TaskType.WATERMARK_ADD: "gemini-flash-mini",
        }
    
    def select_model(self, task_config: TaskConfig) -> Optional[ModelConfig]:
        """작업에 적합한 모델 선택"""
        
        # 1. 비전 모델이 필요한 경우 필터링
        if task_config.requires_vision:
            available_models = {
                name: config 
                for name, config in self.models.items() 
                if config.supports_vision
            }
        else:
            available_models = self.models
        
        # 2. 작업 타입별 기본 모델 확인
        default_model_name = self.task_model_mapping.get(task_config.task_type)
        if default_model_name and default_model_name in available_models:
            model = available_models[default_model_name]
            
            # 예산 확인
            estimated_cost = self._estimate_cost(model, task_config.expected_tokens)
            if self._check_budget(estimated_cost):
                logger.info(
                    f"모델 선택: {model.model_name} "
                    f"(작업: {task_config.task_type}, 예상 비용: ${estimated_cost:.4f})"
                )
                return model
        
        # 3. 복잡도에 따른 대체 모델 선택
        return self._select_by_complexity(task_config, available_models)
    
    def _select_by_complexity(
        self, 
        task_config: TaskConfig, 
        available_models: Dict[str, ModelConfig]
    ) -> Optional[ModelConfig]:
        """복잡도에 따른 모델 선택"""
        
        # 복잡도별 선호 모델
        complexity_preferences = {
            "low": ["gemma-3b", "gemini-flash-mini", "deepseek-r1-7b"],
            "medium": ["deepseek-r1-7b", "qwen-3-14b", "gemini-flash-mini"],
            "high": ["qwen-3-14b", "gemini-flash", "gemini-flash-mini"],
        }
        
        preferences = complexity_preferences.get(
            task_config.complexity, 
            complexity_preferences["medium"]
        )
        
        # 선호도 순서대로 시도
        for model_name in preferences:
            if model_name in available_models:
                model = available_models[model_name]
                estimated_cost = self._estimate_cost(model, task_config.expected_tokens)
                
                if self._check_budget(estimated_cost):
                    logger.info(
                        f"대체 모델 선택: {model.model_name} "
                        f"(복잡도: {task_config.complexity}, 예상 비용: ${estimated_cost:.4f})"
                    )
                    return model
        
        # 무료 모델로 폴백
        return self._fallback_to_free_model(available_models)
    
    def _fallback_to_free_model(
        self, 
        available_models: Dict[str, ModelConfig]
    ) -> Optional[ModelConfig]:
        """무료 모델로 폴백"""
        
        free_models = [
            (name, config)
            for name, config in available_models.items()
            if config.cost_per_1k_tokens == 0
        ]
        
        if free_models:
            # 컨텍스트 윈도우가 큰 모델 우선
            free_models.sort(key=lambda x: x[1].context_window, reverse=True)
            model_name, model = free_models[0]
            
            logger.warning(
                f"예산 초과로 무료 모델 사용: {model.model_name}"
            )
            return model
        
        logger.error("사용 가능한 모델이 없습니다")
        return None
    
    def _estimate_cost(self, model: ModelConfig, expected_tokens: int) -> Decimal:
        """예상 비용 계산"""
        return (Decimal(expected_tokens) / 1000) * model.cost_per_1k_tokens
    
    def _check_budget(self, cost: Decimal) -> bool:
        """예산 확인"""
        if cost == 0:  # 무료 모델
            return True
            
        if self.current_usage + cost > self.monthly_budget:
            logger.warning(
                f"예산 초과: 현재 사용량 ${self.current_usage:.2f} "
                f"+ 예상 비용 ${cost:.4f} > 월 예산 ${self.monthly_budget:.2f}"
            )
            return False
        
        return True
    
    def record_usage(self, model_name: str, actual_tokens: int):
        """실제 사용량 기록"""
        if model_name not in self.models:
            logger.error(f"알 수 없는 모델: {model_name}")
            return
        
        model = self.models[model_name]
        cost = self._estimate_cost(model, actual_tokens)
        self.current_usage += cost
        
        logger.info(
            f"사용량 기록: {model_name} - {actual_tokens} 토큰, "
            f"비용: ${cost:.4f}, 누적: ${self.current_usage:.2f}"
        )
    
    def get_usage_report(self) -> Dict[str, Any]:
        """사용량 리포트"""
        return {
            "monthly_budget": float(self.monthly_budget),
            "current_usage": float(self.current_usage),
            "remaining_budget": float(self.monthly_budget - self.current_usage),
            "usage_percentage": float(
                (self.current_usage / self.monthly_budget * 100) 
                if self.monthly_budget > 0 else 0
            ),
        }
    
    def reset_monthly_usage(self):
        """월간 사용량 초기화"""
        logger.info(f"월간 사용량 초기화: ${self.current_usage:.2f} -> $0.00")
        self.current_usage = Decimal("0.00")