"""
AI 처리 파이프라인 테스트
"""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest

from dropshipping.ai_processors.model_router import ModelRouter
from dropshipping.ai_processors.pipeline import AIProcessingPipeline
from dropshipping.models.product import ProductImage, StandardProduct
from dropshipping.storage.base import BaseStorage


class TestAIProcessingPipeline:
    """AIProcessingPipeline 테스트"""

    @pytest.fixture
    def mock_storage(self):
        """Mock 저장소"""
        storage = Mock(spec=BaseStorage)
        return storage

    @pytest.fixture
    def mock_router(self):
        """Mock 모델 라우터"""
        router = Mock(spec=ModelRouter)
        router.get_usage_report.return_value = {
            "current_usage": 0.05,
            "monthly_budget": 50.0,
            "models_used": {},
        }
        return router

    @pytest.fixture
    def pipeline(self, mock_storage, mock_router):
        """테스트용 파이프라인"""
        return AIProcessingPipeline(
            storage=mock_storage,
            model_router=mock_router,
            config={
                "monthly_ai_budget": 50.0,
                "watermark_text": "TEST",
                "enable_name_enhancement": True,
                "enable_description_generation": True,
                "enable_seo_keywords": True,
                "enable_image_processing": True,
            },
        )

    @pytest.fixture
    def sample_product(self):
        """테스트용 상품"""
        return StandardProduct(
            id="test-001",
            supplier_id="domeme",
            supplier_product_id="DM001",
            name="[도매매] 최신형 블루투스 이어폰 TWS 무선 충전",
            description="고품질 블루투스 이어폰",
            price=15000,
            cost=10000,
            category="전자기기/이어폰",
            images=[
                ProductImage(url="https://example.com/image1.jpg", is_main=True),
                ProductImage(url="https://example.com/image2.jpg", is_main=False),
            ],
            stock_quantity=100,
        )

    def test_init(self, pipeline):
        """초기화 테스트"""
        assert pipeline.enable_name_enhancement is True
        assert pipeline.enable_description_generation is True
        assert pipeline.enable_seo_keywords is True
        assert pipeline.enable_image_processing is True
        assert pipeline.stats["products_processed"] == 0

    @pytest.mark.asyncio
    async def test_process_product_basic(self, pipeline, sample_product):
        """기본 상품 처리 테스트"""
        # Mock ProductEnhancer
        with patch.object(
            pipeline.product_enhancer, "process", new_callable=AsyncMock
        ) as mock_enhance:
            mock_enhance.return_value = {
                "enhancements": {
                    "enhanced_name": "블루투스 이어폰 TWS 무선 충전",
                    "generated_description": "<h3>제품 특징</h3><ul><li>최신 블루투스 5.0</li></ul>",
                    "seo_keywords": ["블루투스이어폰", "무선이어폰", "TWS"],
                }
            }

            # Mock ImageProcessor
            with patch.object(
                pipeline, "_process_product_images", new_callable=AsyncMock
            ) as mock_images:
                mock_images.return_value = {
                    "image_0": {
                        "original_url": "https://example.com/image1.jpg",
                        "caption": "블루투스 이어폰 메인 이미지",
                        "processed_images": {"watermarked": "processed/test-001_wm_0.png"},
                    }
                }

                result = await pipeline.process_product(sample_product)

        assert result["product_id"] == "test-001"
        assert "enhancements" in result
        assert "processed_images" in result
        assert result["errors"] == []
        assert result["processing_time"] is not None
        assert result["ai_cost"] == Decimal("0.05")

        # 통계 확인
        assert pipeline.stats["products_processed"] == 1
        assert pipeline.stats["ai_enhancements"] == 3
        assert pipeline.stats["images_processed"] == 1

    @pytest.mark.asyncio
    async def test_process_product_from_dict(self, pipeline):
        """딕셔너리로부터 상품 처리 테스트"""
        product_dict = {
            "id": "dict-001",
            "supplier_id": "test",
            "supplier_product_id": "TEST001",
            "name": "테스트 상품",
            "description": "설명",
            "price": 10000,
            "cost": 5000,
            "category": "기타",
            "images": [],
            "stock_quantity": 10,
        }

        with patch.object(
            pipeline.product_enhancer, "process", new_callable=AsyncMock
        ) as mock_enhance:
            mock_enhance.return_value = {"enhancements": {}}

            result = await pipeline.process_product(product_dict)

        assert result["product_id"] == "dict-001"
        assert result["original_data"]["name"] == "테스트 상품"

    @pytest.mark.asyncio
    async def test_enhance_product_info_selective(self, pipeline, sample_product):
        """선택적 정보 향상 테스트"""
        # 이름 향상만 활성화
        pipeline.enable_description_generation = False
        pipeline.enable_seo_keywords = False

        with patch.object(
            pipeline.product_enhancer, "process", new_callable=AsyncMock
        ) as mock_enhance:
            mock_enhance.return_value = {"enhancements": {"enhanced_name": "개선된 상품명"}}

            result = await pipeline._enhance_product_info(
                sample_product, {"enhance_name": True, "generate_description": False}
            )

        assert "enhanced_name" in result
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_process_product_with_error(self, pipeline, sample_product):
        """오류 처리 테스트"""
        # process_product 메서드에서 예외를 발생시키도록 수정
        with patch.object(
            pipeline, "_enhance_product_info", new_callable=AsyncMock
        ) as mock_enhance:
            mock_enhance.side_effect = Exception("AI 처리 실패")

            result = await pipeline.process_product(sample_product)

        assert result["product_id"] == "test-001"
        assert len(result["errors"]) > 0
        assert "AI 처리 실패" in result["errors"][0]
        assert pipeline.stats["products_failed"] == 1

    @pytest.mark.asyncio
    async def test_save_enhanced_product(self, pipeline, sample_product):
        """향상된 상품 저장 테스트"""
        processing_result = {
            "enhancements": {
                "enhanced_name": "개선된 상품명",
                "generated_description": "개선된 설명",
                "seo_keywords": ["키워드1", "키워드2"],
            },
            "processed_images": {"image_0": {"watermarked": "path/to/image.png"}},
            "processing_time": 1.5,
            "ai_cost": Decimal("0.01"),
        }

        await pipeline._save_enhanced_product(sample_product, processing_result)

        assert sample_product.name == "개선된 상품명"
        assert sample_product.description == "개선된 설명"
        assert sample_product.tags == ["키워드1", "키워드2"]
        assert "processed_images" in sample_product.attributes
        assert "ai_processed" in sample_product.attributes

    @pytest.mark.asyncio
    async def test_process_batch(self, pipeline):
        """배치 처리 테스트"""
        products = [
            StandardProduct(
                id=f"batch-{i}",
                supplier_id="test",
                supplier_product_id=f"TEST{i:03d}",
                name=f"상품 {i}",
                description="설명",
                price=10000,
                cost=5000,
                category="기타",
                images=[],
                stock_quantity=10,
            )
            for i in range(3)
        ]

        with patch.object(pipeline, "process_product", new_callable=AsyncMock) as mock_process:
            mock_process.side_effect = [
                {"product_id": "batch-0", "errors": []},
                {"product_id": "batch-1", "errors": []},
                Exception("배치 처리 오류"),
            ]

            results = await pipeline.process_batch(products, max_concurrent=2)

        assert len(results) == 2
        assert results[0]["product_id"] == "batch-0"
        assert results[1]["product_id"] == "batch-1"
        assert pipeline.stats["products_failed"] == 1

    def test_get_stats(self, pipeline):
        """통계 조회 테스트"""
        pipeline.stats = {
            "products_processed": 10,
            "products_failed": 2,
            "ai_enhancements": 30,
            "images_processed": 20,
            "total_cost": Decimal("0.50"),
        }

        with patch.object(pipeline.product_enhancer, "get_stats") as mock_enhancer_stats:
            mock_enhancer_stats.return_value = {"total_tokens": 1000}

            with patch.object(pipeline.image_processor, "get_stats") as mock_image_stats:
                mock_image_stats.return_value = {"processed": 20}

                stats = pipeline.get_stats()

        assert stats["products_processed"] == 10
        assert stats["products_failed"] == 2
        assert stats["success_rate"] == 10 / 12
        assert "ai_usage" in stats
        assert "enhancer_stats" in stats
        assert "image_processor_stats" in stats

    def test_reset_stats(self, pipeline):
        """통계 초기화 테스트"""
        pipeline.stats["products_processed"] = 100

        with patch.object(pipeline.product_enhancer, "reset_stats") as mock_enhancer_reset:
            with patch.object(pipeline.image_processor, "reset_stats") as mock_image_reset:
                pipeline.reset_stats()

        assert pipeline.stats["products_processed"] == 0
        assert pipeline.stats["products_failed"] == 0
        mock_enhancer_reset.assert_called_once()
        mock_image_reset.assert_called_once()

    def test_log_pipeline_run(self, pipeline):
        """파이프라인 실행 로그 테스트"""
        # 예외가 발생하지 않으면 성공
        pipeline.log_pipeline_run("completed", {"extra": "data"})

        # 로그 실패시에도 예외가 발생하지 않아야 함
        with patch("dropshipping.ai_processors.pipeline.logger.error") as mock_error:
            with patch(
                "dropshipping.ai_processors.pipeline.logger.info",
                side_effect=Exception("로그 오류"),
            ):
                pipeline.log_pipeline_run("failed")

            mock_error.assert_called()
