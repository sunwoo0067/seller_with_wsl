"""
AI 처리 파이프라인
상품 데이터의 AI 처리를 조율하는 통합 파이프라인
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from dropshipping.ai_processors import (
    ModelRouter,
    ProductEnhancer,
)
from dropshipping.ai_processors.image_processor import ImageProcessor
from dropshipping.models.product import StandardProduct
from dropshipping.storage.base import BaseStorage


class AIProcessingPipeline:
    """AI 처리 파이프라인"""

    def __init__(
        self,
        storage: BaseStorage,
        model_router: Optional[ModelRouter] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        초기화

        Args:
            storage: 저장소 인스턴스
            model_router: AI 모델 라우터
            config: 파이프라인 설정
        """
        self.storage = storage
        self.config = config or {}

        # 모델 라우터 (월 예산 설정)
        monthly_budget = Decimal(str(self.config.get("monthly_ai_budget", 50.0)))
        self.model_router = model_router or ModelRouter(monthly_budget=monthly_budget)

        # AI 프로세서들
        self.product_enhancer = ProductEnhancer(model_router=self.model_router)
        self.image_processor = ImageProcessor(
            model_router=self.model_router,
            watermark_text=self.config.get("watermark_text", "dropshipping.com"),
        )

        # 파이프라인 설정
        self.enable_name_enhancement = self.config.get("enable_name_enhancement", True)
        self.enable_description_generation = self.config.get("enable_description_generation", True)
        self.enable_seo_keywords = self.config.get("enable_seo_keywords", True)
        self.enable_image_processing = self.config.get("enable_image_processing", True)

        # 통계
        self.stats = {
            "products_processed": 0,
            "products_failed": 0,
            "ai_enhancements": 0,
            "images_processed": 0,
            "total_cost": Decimal("0.00"),
        }

    async def process_product(
        self,
        product: Union[StandardProduct, Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        단일 상품 AI 처리

        Args:
            product: 처리할 상품
            options: 처리 옵션

        Returns:
            처리 결과
        """
        options = options or {}

        # StandardProduct로 변환
        if isinstance(product, dict):
            product = StandardProduct(**product)

        logger.info(f"상품 AI 처리 시작: {product.id} - {product.name[:50]}...")

        result = {
            "product_id": product.id,
            "original_data": {
                "name": product.name,
                "description": product.description,
                "images": len(product.images),
            },
            "enhancements": {},
            "processed_images": {},
            "errors": [],
            "processing_time": None,
            "ai_cost": Decimal("0.00"),
        }

        start_time = datetime.now()

        try:
            # 1. 상품 정보 향상
            if any(
                [
                    self.enable_name_enhancement,
                    self.enable_description_generation,
                    self.enable_seo_keywords,
                ]
            ):
                enhancement_result = await self._enhance_product_info(product, options)
                result["enhancements"] = enhancement_result

            # 2. 이미지 처리
            if self.enable_image_processing and product.images:
                image_results = await self._process_product_images(product, options)
                result["processed_images"] = image_results

            # 3. 처리된 상품 저장
            if options.get("save_to_storage", True):
                await self._save_enhanced_product(product, result)

            # 통계 업데이트
            self.stats["products_processed"] += 1
            self.stats["ai_enhancements"] += len(result["enhancements"])
            self.stats["images_processed"] += len(result["processed_images"])

            # 처리 시간 계산
            result["processing_time"] = (datetime.now() - start_time).total_seconds()

            # AI 비용 계산
            result["ai_cost"] = self._calculate_cost()

            logger.info(
                f"상품 AI 처리 완료: {product.id} "
                f"(시간: {result['processing_time']:.1f}초, 비용: ${result['ai_cost']:.4f})"
            )

        except Exception as e:
            logger.error(f"상품 AI 처리 실패: {product.id} - {str(e)}")
            result["errors"].append(str(e))
            self.stats["products_failed"] += 1

        return result

    async def _enhance_product_info(
        self, product: StandardProduct, options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """상품 정보 향상"""

        enhancements = {}

        # 향상 타입 결정
        enhance_types = []
        if self.enable_name_enhancement and options.get("enhance_name", True):
            enhance_types.append("name")
        if self.enable_description_generation and options.get("generate_description", True):
            enhance_types.append("description")
        if self.enable_seo_keywords and options.get("extract_seo", True):
            enhance_types.append("seo")

        if not enhance_types:
            return enhancements

        # ProductEnhancer 실행
        for enhance_type in enhance_types:
            try:
                result = await self.product_enhancer.process(product, enhance_type=enhance_type)

                if "enhancements" in result:
                    enhancements.update(result["enhancements"])

            except Exception as e:
                logger.error(f"상품 정보 향상 실패 ({enhance_type}): {str(e)}")

        return enhancements

    async def _process_product_images(
        self, product: StandardProduct, options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """상품 이미지 처리"""

        processed_images = {}

        # 처리할 이미지 선택 (최대 5개)
        images_to_process = [
            img for img in product.images if img.url and (img.is_main or len(product.images) <= 5)
        ][:5]

        if not images_to_process:
            return processed_images

        # 이미지 처리 타입
        process_type = "all"  # caption, background, watermark
        if options.get("skip_background_removal"):
            process_type = "watermark"

        # 각 이미지 처리
        for idx, image in enumerate(images_to_process):
            try:
                # 실제로는 이미지 URL에서 다운로드 필요
                # 여기서는 시뮬레이션
                result = {
                    "original_url": str(image.url),
                    "caption": f"상품 이미지 {idx + 1}",
                    "processed_images": {"watermarked": f"processed/{product.id}_wm_{idx}.png"},
                }

                processed_images[f"image_{idx}"] = result

            except Exception as e:
                logger.error(f"이미지 처리 실패: {image.url} - {str(e)}")

        return processed_images

    async def _save_enhanced_product(
        self, product: StandardProduct, processing_result: Dict[str, Any]
    ):
        """향상된 상품 정보 저장"""

        try:
            # 향상된 정보로 상품 업데이트
            enhancements = processing_result.get("enhancements", {})

            if "enhanced_name" in enhancements:
                product.name = enhancements["enhanced_name"]

            if "generated_description" in enhancements:
                product.description = enhancements["generated_description"]

            if "seo_keywords" in enhancements:
                product.tags = enhancements["seo_keywords"]

            # 처리된 이미지 정보 추가
            if processing_result.get("processed_images"):
                if not product.attributes:
                    product.attributes = {}
                product.attributes["processed_images"] = processing_result["processed_images"]

            # AI 처리 메타데이터
            product.attributes["ai_processed"] = {
                "processed_at": datetime.now().isoformat(),
                "enhancements": list(enhancements.keys()),
                "processing_time": processing_result.get("processing_time"),
                "ai_cost": float(processing_result.get("ai_cost", 0)),
            }

            # 저장
            # 실제로는 storage.save_processed_product() 호출
            logger.info(f"향상된 상품 정보 저장: {product.id}")

        except Exception as e:
            logger.error(f"향상된 상품 저장 실패: {str(e)}")
            raise

    def _calculate_cost(self) -> Decimal:
        """현재 세션의 AI 비용 계산"""

        # 각 프로세서의 사용량 합계
        enhancer_usage = self.product_enhancer.get_stats()
        image_usage = self.image_processor.get_stats()

        total_tokens = enhancer_usage.get("total_tokens", 0) + image_usage.get("total_tokens", 0)

        # 모델 라우터에서 현재 사용량 가져오기
        usage_report = self.model_router.get_usage_report()
        return Decimal(str(usage_report["current_usage"]))

    async def process_batch(
        self,
        products: List[Union[StandardProduct, Dict[str, Any]]],
        options: Optional[Dict[str, Any]] = None,
        max_concurrent: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        여러 상품 배치 처리

        Args:
            products: 처리할 상품 목록
            options: 처리 옵션
            max_concurrent: 최대 동시 처리 수

        Returns:
            처리 결과 목록
        """
        logger.info(f"{len(products)}개 상품 배치 AI 처리 시작")

        # 세마포어로 동시 처리 제한
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(product):
            async with semaphore:
                return await self.process_product(product, options)

        # 동시 처리
        results = await asyncio.gather(
            *[process_with_semaphore(product) for product in products], return_exceptions=True
        )

        # 결과 필터링
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"배치 처리 오류: {str(result)}")
                self.stats["products_failed"] += 1
            else:
                valid_results.append(result)

        logger.info(
            f"배치 AI 처리 완료: "
            f"성공 {len(valid_results)}, 실패 {len(products) - len(valid_results)}"
        )

        return valid_results

    def get_stats(self) -> Dict[str, Any]:
        """파이프라인 통계"""

        # 사용량 리포트
        usage_report = self.model_router.get_usage_report()

        return {
            **self.stats,
            "success_rate": (
                self.stats["products_processed"]
                / (self.stats["products_processed"] + self.stats["products_failed"])
                if self.stats["products_processed"] + self.stats["products_failed"] > 0
                else 0
            ),
            "ai_usage": usage_report,
            "enhancer_stats": self.product_enhancer.get_stats(),
            "image_processor_stats": self.image_processor.get_stats(),
        }

    def reset_stats(self):
        """통계 초기화"""
        self.stats = {
            "products_processed": 0,
            "products_failed": 0,
            "ai_enhancements": 0,
            "images_processed": 0,
            "total_cost": Decimal("0.00"),
        }

        self.product_enhancer.reset_stats()
        self.image_processor.reset_stats()

    def log_pipeline_run(self, status: str, details: Optional[Dict[str, Any]] = None):
        """파이프라인 실행 로그"""

        try:
            log_data = {
                "pipeline_type": "ai_processing",
                "target_type": "product",
                "target_id": "batch",
                "status": status,
                "details": {
                    **self.stats,
                    **(details or {}),
                    "timestamp": datetime.now().isoformat(),
                },
            }

            # 실제로는 storage.log_pipeline() 호출
            logger.info(f"파이프라인 로그: {status}")

        except Exception as e:
            logger.error(f"파이프라인 로그 실패: {str(e)}")
