"""
AI 프로세서 기반 클래스
모든 AI 처리기의 추상 인터페이스
"""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from dropshipping.ai_processors.model_router import (
    ModelConfig,
    ModelProvider,
    ModelRouter,
    TaskConfig,
)
from dropshipping.models.product import StandardProduct


class AIProcessingError(Exception):
    """AI 처리 오류"""

    pass


class BaseAIProcessor(ABC):
    """AI 프로세서 추상 클래스"""

    def __init__(
        self,
        model_router: Optional[ModelRouter] = None,
        default_task_config: Optional[TaskConfig] = None,
    ):
        """
        Args:
            model_router: AI 모델 라우터
            default_task_config: 기본 작업 설정
        """
        self.model_router = model_router or ModelRouter()
        self.default_task_config = default_task_config

        # 통계
        self.stats = {
            "processed": 0,
            "failed": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
        }

    @abstractmethod
    async def process(
        self,
        data: Union[StandardProduct, Dict[str, Any], str],
        task_config: Optional[TaskConfig] = None,
        **kwargs,
    ) -> Any:
        """
        AI 처리 실행

        Args:
            data: 처리할 데이터
            task_config: 작업 설정 (없으면 기본값 사용)
            **kwargs: 추가 파라미터

        Returns:
            처리 결과
        """
        pass

    @abstractmethod
    def validate_input(self, data: Any) -> bool:
        """입력 데이터 검증"""
        pass

    @abstractmethod
    def prepare_prompt(self, data: Any, **kwargs) -> str:
        """프롬프트 준비"""
        pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type(AIProcessingError),
    )
    async def _execute_with_model(
        self, model_config: ModelConfig, prompt: str, system_prompt: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """모델 실행 (재시도 포함)"""

        try:
            if model_config.provider == ModelProvider.OLLAMA:
                result = await self._execute_ollama(model_config, prompt, system_prompt, **kwargs)
            elif model_config.provider == ModelProvider.GEMINI:
                result = await self._execute_gemini(model_config, prompt, system_prompt, **kwargs)
            else:
                raise ValueError(f"지원하지 않는 모델 제공자: {model_config.provider}")

            # 사용량 기록
            if "usage" in result:
                tokens = result["usage"].get("total_tokens", 0)
                self.model_router.record_usage(model_config.model_name, tokens)
                self.stats["total_tokens"] += tokens

            return result

        except Exception as e:
            logger.error(f"모델 실행 실패: {str(e)}")
            raise AIProcessingError(f"모델 실행 실패: {str(e)}")

    async def _execute_ollama(
        self, model_config: ModelConfig, prompt: str, system_prompt: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """Ollama 모델 실행"""

        try:
            import ollama

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # 동기 함수를 비동기로 실행
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: ollama.chat(
                    model=model_config.model_name,
                    messages=messages,
                    options={
                        "temperature": model_config.temperature,
                        "num_predict": model_config.max_tokens,
                    },
                ),
            )

            # 응답 포맷 통일
            return {
                "content": response["message"]["content"],
                "model": model_config.model_name,
                "usage": {
                    "total_tokens": response.get("eval_count", 0)
                    + response.get("prompt_eval_count", 0),
                    "prompt_tokens": response.get("prompt_eval_count", 0),
                    "completion_tokens": response.get("eval_count", 0),
                },
                "raw_response": response,
            }

        except ImportError:
            logger.error("Ollama 패키지가 설치되어 있지 않습니다")
            raise AIProcessingError("Ollama를 사용할 수 없습니다")
        except Exception as e:
            logger.error(f"Ollama 실행 오류: {str(e)}")
            raise AIProcessingError(f"Ollama 실행 오류: {str(e)}")

    async def _execute_gemini(
        self, model_config: ModelConfig, prompt: str, system_prompt: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """Gemini 모델 실행"""

        try:
            import google.generativeai as genai

            from dropshipping.config import settings

            # API 키 설정
            genai.configure(api_key=settings.GOOGLE_API_KEY)

            # 모델 초기화
            model = genai.GenerativeModel(
                model_name=model_config.model_name,
                generation_config={
                    "temperature": model_config.temperature,
                    "max_output_tokens": model_config.max_tokens,
                },
            )

            # 프롬프트 조합
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"

            # 생성
            response = await model.generate_content_async(full_prompt)

            # 토큰 수 추정 (Gemini는 정확한 토큰 수를 제공하지 않음)
            estimated_tokens = len(full_prompt.split()) + len(response.text.split())

            return {
                "content": response.text,
                "model": model_config.model_name,
                "usage": {
                    "total_tokens": estimated_tokens,
                    "prompt_tokens": len(full_prompt.split()),
                    "completion_tokens": len(response.text.split()),
                },
                "raw_response": response,
            }

        except ImportError:
            logger.error("Google Generative AI 패키지가 설치되어 있지 않습니다")
            raise AIProcessingError("Gemini를 사용할 수 없습니다")
        except Exception as e:
            logger.error(f"Gemini 실행 오류: {str(e)}")
            raise AIProcessingError(f"Gemini 실행 오류: {str(e)}")

    def parse_json_response(self, content: str) -> Dict[str, Any]:
        """JSON 응답 파싱"""

        # JSON 블록 추출 시도
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            if end > start:
                content = content[start:end].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {str(e)}\n내용: {content[:200]}...")

            # 간단한 복구 시도
            content = content.strip()
            if not content.startswith("{"):
                content = "{" + content
            if not content.endswith("}"):
                content = content + "}"

            try:
                return json.loads(content)
            except json.JSONDecodeError:
                raise AIProcessingError("JSON 응답 파싱 실패")

    async def process_batch(
        self,
        items: List[Any],
        task_config: Optional[TaskConfig] = None,
        max_concurrent: int = 5,
        **kwargs,
    ) -> List[Any]:
        """배치 처리"""

        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(item):
            async with semaphore:
                try:
                    return await self.process(item, task_config, **kwargs)
                except Exception as e:
                    logger.error(f"항목 처리 실패: {str(e)}")
                    self.stats["failed"] += 1
                    return None

        # 동시 처리
        results = await asyncio.gather(
            *[process_with_semaphore(item) for item in items], return_exceptions=True
        )

        # 성공한 결과만 반환
        return [r for r in results if r is not None and not isinstance(r, Exception)]

    def get_stats(self) -> Dict[str, Any]:
        """처리 통계 반환"""
        return {
            **self.stats,
            "success_rate": (
                self.stats["processed"] / (self.stats["processed"] + self.stats["failed"])
                if self.stats["processed"] + self.stats["failed"] > 0
                else 0
            ),
            "usage_report": self.model_router.get_usage_report(),
        }

    def reset_stats(self):
        """통계 초기화"""
        self.stats = {
            "processed": 0,
            "failed": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
        }
