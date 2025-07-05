"""
이미지 프로세서 테스트
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from PIL import Image
import io
import base64

from dropshipping.ai_processors.image_processor import ImageProcessor
from dropshipping.ai_processors.model_router import ModelRouter, TaskConfig, TaskType


class TestImageProcessor:
    """ImageProcessor 테스트"""
    
    @pytest.fixture
    def mock_router(self):
        """Mock 모델 라우터"""
        router = Mock(spec=ModelRouter)
        router.select_model.return_value = Mock(
            model_name="gemini-flash",
            provider="gemini",
            supports_vision=True
        )
        return router
    
    @pytest.fixture
    def processor(self, mock_router):
        """테스트용 프로세서"""
        return ImageProcessor(
            model_router=mock_router,
            watermark_text="TEST",
            watermark_opacity=128
        )
    
    @pytest.fixture
    def test_image(self):
        """테스트용 이미지"""
        # 100x100 빨간색 이미지 생성
        image = Image.new('RGB', (100, 100), color='red')
        return image
    
    @pytest.fixture
    def test_image_path(self, tmp_path, test_image):
        """테스트용 이미지 파일"""
        image_path = tmp_path / "test_image.png"
        test_image.save(image_path)
        return image_path
    
    def test_init(self, processor):
        """초기화 테스트"""
        assert processor.watermark_text == "TEST"
        assert processor.watermark_opacity == 128
        assert processor.output_dir.exists()
        assert len(processor.supported_formats) > 0
    
    def test_validate_input(self, processor, test_image_path, test_image):
        """입력 검증 테스트"""
        # 파일 경로
        assert processor.validate_input(test_image_path) is True
        assert processor.validate_input(str(test_image_path)) is True
        
        # PIL Image
        assert processor.validate_input(test_image) is True
        
        # 딕셔너리
        assert processor.validate_input({"image_path": str(test_image_path)}) is True
        assert processor.validate_input({"image_data": "base64data"}) is True
        
        # 잘못된 입력
        assert processor.validate_input("nonexistent.png") is False
        assert processor.validate_input(123) is False
        assert processor.validate_input({}) is False
    
    def test_load_image_from_path(self, processor, test_image_path):
        """경로에서 이미지 로드 테스트"""
        image, path = processor._load_image(test_image_path)
        assert image is not None
        assert path == test_image_path
        assert image.size == (100, 100)
    
    def test_load_image_from_pil(self, processor, test_image):
        """PIL Image 로드 테스트"""
        image, path = processor._load_image(test_image)
        assert image is test_image
        assert path is None
    
    def test_load_image_from_dict(self, processor, test_image_path):
        """딕셔너리에서 이미지 로드 테스트"""
        # 파일 경로
        data = {"image_path": str(test_image_path)}
        image, path = processor._load_image(data)
        assert image is not None
        assert path == test_image_path
        
        # Base64 데이터
        buffer = io.BytesIO()
        test_image = Image.new('RGB', (50, 50), color='blue')
        test_image.save(buffer, format='PNG')
        base64_data = base64.b64encode(buffer.getvalue()).decode()
        
        data = {"image_data": base64_data}
        image, path = processor._load_image(data)
        assert image is not None
        assert path is None
        assert image.size == (50, 50)
    
    def test_add_watermark(self, processor, test_image):
        """워터마크 추가 테스트"""
        watermarked = processor._add_watermark(test_image)
        
        assert watermarked is not None
        assert watermarked.size == test_image.size
        assert watermarked.mode == 'RGBA'
        
        # 워터마크가 추가되었는지 확인 (픽셀이 변경됨)
        # 실제로는 더 정교한 검증 필요
        assert watermarked != test_image
    
    def test_save_image(self, processor, test_image):
        """이미지 저장 테스트"""
        # PNG 저장
        path = processor._save_image(test_image, "test", "png", 95)
        assert path.exists()
        assert path.suffix == ".png"
        
        # JPEG 저장
        path = processor._save_image(test_image, "test", "jpg", 85)
        assert path.exists()
        assert path.suffix == ".jpg"
        
        # WebP 저장
        path = processor._save_image(test_image, "test", "webp", 90)
        assert path.exists()
        assert path.suffix == ".webp"
    
    @pytest.mark.asyncio
    @patch('dropshipping.ai_processors.image_processor.ImageProcessor._execute_with_model')
    async def test_generate_caption(self, mock_execute_with_model, processor, test_image):
        """캡션 생성 테스트"""
        mock_execute_with_model.return_value = {"content": "Mocked image caption", "usage": {"total_tokens": 50}}

        config = TaskConfig(
            task_type=TaskType.IMAGE_CAPTION,
            requires_vision=True
        )
        
        caption = await processor._generate_caption(test_image, config)
        assert isinstance(caption, str)
        assert caption == "Mocked image caption"
        mock_execute_with_model.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('dropshipping.ai_processors.image_processor.ImageProcessor._execute_with_model')
    async def test_remove_background(self, mock_execute_with_model, processor, test_image):
        """배경 제거 테스트"""
        # Mocked PIL Image 반환
        # 실제 PNG 이미지 데이터를 Base64로 인코딩하여 반환
        green_image = Image.new('RGBA', (100, 100), color='green')
        buffered = io.BytesIO()
        green_image.save(buffered, format="PNG")
        encoded_image = base64.b64encode(buffered.getvalue()).decode()

        mock_execute_with_model.return_value = {
            "image_data": encoded_image,
            "usage": {"total_tokens": 100}
        }

        config = TaskConfig(
            task_type=TaskType.BACKGROUND_REMOVE,
            requires_vision=True
        )
        
        result = await processor._remove_background(test_image, config)
        assert result is not None
        assert result.mode == 'RGBA'
        mock_execute_with_model.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_all(self, processor, test_image_path):
        """전체 처리 테스트"""
        result = await processor.process(
            test_image_path,
            process_type="all"
        )
        
        assert "original_path" in result
        assert "original_size" in result
        assert "caption" in result
        assert "processed_images" in result
        assert "processed_at" in result
        
        # 처리된 이미지 확인
        assert "watermarked" in result["processed_images"]
        
        # 통계 업데이트 확인
        assert processor.stats["processed"] == 1
    
    @pytest.mark.asyncio
    async def test_process_watermark_only(self, processor, test_image):
        """워터마크만 처리 테스트"""
        result = await processor.process(
            test_image,
            process_type="watermark"
        )
        
        assert "caption" not in result
        assert "watermarked" in result["processed_images"]
    
    @pytest.mark.asyncio
    async def test_process_with_options(self, processor, test_image):
        """옵션 설정 처리 테스트"""
        result = await processor.process(
            test_image,
            process_type="watermark",
            output_format="jpg",
            quality=80
        )
        
        watermark_path = Path(result["processed_images"]["watermarked"])
        assert watermark_path.suffix == ".jpg"
    
    @pytest.mark.asyncio
    async def test_process_batch_images(self, processor, tmp_path):
        """배치 이미지 처리 테스트"""
        # 여러 테스트 이미지 생성
        image_paths = []
        for i in range(3):
            image = Image.new('RGB', (100, 100), color=['red', 'green', 'blue'][i])
            path = tmp_path / f"test_{i}.png"
            image.save(path)
            image_paths.append(path)
        
        results = await processor.process_batch_images(
            image_paths,
            process_type="watermark",
            max_concurrent=2
        )
        
        assert len(results) == 3
        for result in results:
            assert "processed_images" in result
            assert "watermarked" in result["processed_images"]
    
    def test_cleanup_processed_images(self, processor, tmp_path):
        """오래된 이미지 정리 테스트"""
        # 오래된 파일 생성
        import time
        old_file = processor.output_dir / "old_file.png"
        old_file.touch()
        
        # 파일 시간 수정 (8일 전으로)
        old_time = time.time() - (8 * 24 * 60 * 60)
        os.utime(old_file, (old_time, old_time))
        
        # 새 파일 생성
        new_file = processor.output_dir / "new_file.png"
        new_file.touch()
        
        # 7일 이상 된 파일 정리
        removed = processor.cleanup_processed_images(days=7)
        
        assert removed == 1
        assert not old_file.exists()
        assert new_file.exists()
        
        # 정리
        new_file.unlink()
    
    @pytest.mark.asyncio
    async def test_process_invalid_input(self, processor):
        """잘못된 입력 처리 테스트"""
        with pytest.raises(Exception):
            await processor.process("nonexistent_file.png")
    
    def test_get_stats(self, processor):
        """통계 조회 테스트"""
        stats = processor.get_stats()
        assert "processed" in stats
        assert "failed" in stats
        assert "success_rate" in stats
        assert "usage_report" in stats


# 필요한 import 추가
import os