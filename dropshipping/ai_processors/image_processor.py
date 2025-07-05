"""
이미지 처리 프로세서
배경 제거, 워터마크 추가, 이미지 캡션 생성
"""

import os
import io
import base64
from typing import Dict, Any, Optional, List, Union, Tuple
from pathlib import Path
import hashlib
from datetime import datetime

from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from dropshipping.ai_processors.base import BaseAIProcessor, AIProcessingError
from dropshipping.ai_processors.model_router import TaskConfig, TaskType


class ImageProcessor(BaseAIProcessor):
    """이미지 처리 프로세서"""
    
    def __init__(
        self, 
        model_router=None,
        watermark_text: str = "dropshipping.com",
        watermark_opacity: int = 128
    ):
        """
        초기화
        
        Args:
            model_router: AI 모델 라우터
            watermark_text: 워터마크 텍스트
            watermark_opacity: 워터마크 투명도 (0-255)
        """
        # 기본 작업 설정
        default_config = TaskConfig(
            task_type=TaskType.IMAGE_CAPTION,
            complexity="medium",
            expected_tokens=200,
            requires_vision=True,
        )
        super().__init__(model_router, default_config)
        
        self.watermark_text = watermark_text
        self.watermark_opacity = watermark_opacity
        
        # 지원 이미지 포맷
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        
        # 출력 디렉터리
        self.output_dir = Path("./processed_images")
        self.output_dir.mkdir(exist_ok=True)
    
    async def process(
        self,
        data: Union[str, Path, Image.Image, Dict[str, Any]],
        task_config: Optional[TaskConfig] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        이미지 처리 실행
        
        Args:
            data: 이미지 경로, PIL Image, 또는 이미지 정보 딕셔너리
            task_config: 작업 설정
            **kwargs: 추가 파라미터
                - process_type: "all", "caption", "background", "watermark"
                - output_format: "png", "jpg", "webp"
                - quality: 이미지 품질 (1-100)
        """
        # 입력 검증
        if not self.validate_input(data):
            raise AIProcessingError("유효하지 않은 입력 데이터")
        
        # 이미지 로드
        image, image_path = self._load_image(data)
        if not image:
            raise AIProcessingError("이미지를 로드할 수 없습니다")
        
        # 작업 설정
        config = task_config or self.default_task_config
        process_type = kwargs.get("process_type", "all")
        output_format = kwargs.get("output_format", "png")
        quality = kwargs.get("quality", 95)
        
        results = {
            "original_path": str(image_path) if image_path else None,
            "original_size": image.size,
            "processed_images": {}
        }
        
        # 이미지 캡션 생성
        if process_type in ["all", "caption"]:
            caption = await self._generate_caption(image, config)
            results["caption"] = caption
        
        # 배경 제거
        if process_type in ["all", "background"]:
            bg_removed = await self._remove_background(image, config)
            if bg_removed:
                bg_path = self._save_image(
                    bg_removed, 
                    "background_removed", 
                    output_format, 
                    quality
                )
                results["processed_images"]["background_removed"] = str(bg_path)
        
        # 워터마크 추가
        if process_type in ["all", "watermark"]:
            watermarked = self._add_watermark(image)
            wm_path = self._save_image(
                watermarked, 
                "watermarked", 
                output_format, 
                quality
            )
            results["processed_images"]["watermarked"] = str(wm_path)
        
        # 통계 업데이트
        self.stats["processed"] += 1
        
        results["processed_at"] = datetime.now().isoformat()
        return results
    
    def validate_input(self, data: Any) -> bool:
        """입력 검증"""
        if isinstance(data, (str, Path)):
            path = Path(data)
            return path.exists() and path.suffix.lower() in self.supported_formats
        elif isinstance(data, Image.Image):
            return True
        elif isinstance(data, dict):
            return "image_path" in data or "image_data" in data
        return False
    
    def prepare_prompt(self, data: Any, **kwargs) -> str:
        """프롬프트 준비"""
        # 구체적인 메서드에서 구현
        pass
    
    def _load_image(self, data: Union[str, Path, Image.Image, Dict]) -> Tuple[Optional[Image.Image], Optional[Path]]:
        """이미지 로드"""
        try:
            if isinstance(data, (str, Path)):
                path = Path(data)
                image = Image.open(path)
                return image, path
            
            elif isinstance(data, Image.Image):
                return data, None
            
            elif isinstance(data, dict):
                if "image_path" in data:
                    path = Path(data["image_path"])
                    image = Image.open(path)
                    return image, path
                
                elif "image_data" in data:
                    # Base64 인코딩된 데이터
                    image_data = base64.b64decode(data["image_data"])
                    image = Image.open(io.BytesIO(image_data))
                    return image, None
            
            return None, None
            
        except Exception as e:
            logger.error(f"이미지 로드 실패: {str(e)}")
            return None, None
    
    async def _generate_caption(
        self, 
        image: Image.Image,
        config: TaskConfig
    ) -> str:
        """이미지 캡션 생성"""
        
        # 작업 타입 설정
        config.task_type = TaskType.IMAGE_CAPTION
        config.requires_vision = True
        
        # 모델 선택
        model = self.model_router.select_model(config)
        if not model:
            logger.error("이미지 캡션용 모델을 찾을 수 없습니다")
            return ""
        
        # 이미지를 base64로 인코딩
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        image_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        # 프롬프트 준비
        prompt = """다음 이미지를 분석하고 상품 설명에 적합한 캡션을 생성하세요:
1. 이미지의 주요 객체와 특징 설명
2. 색상, 재질, 스타일 언급
3. 상품의 용도나 사용 상황 추측
4. 50-100자 내외로 간결하게 작성"""
        
        try:
            # 모델 실행 (실제로는 이미지와 함께 전송)
            logger.info(f"이미지 캡션 생성 중... (모델: {model.model_name})")
            
            result = await self._execute_with_model(
                model, prompt, image=image_base64
            )
            
            caption = result["content"].strip()
            
            logger.info(f"캡션 생성 완료: {caption}")
            return caption
            
        except Exception as e:
            logger.error(f"캡션 생성 실패: {str(e)}")
            return ""
    
    async def _remove_background(
        self,
        image: Image.Image,
        config: TaskConfig
    ) -> Optional[Image.Image]:
        """배경 제거"""
        
        # 작업 타입 설정
        config.task_type = TaskType.BACKGROUND_REMOVE
        config.requires_vision = True
        config.complexity = "high"
        
        # 모델 선택
        model = self.model_router.select_model(config)
        if not model:
            logger.error("배경 제거용 모델을 찾을 수 없습니다")
            return None
        
        # 이미지를 base64로 인코딩
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        image_base64 = base64.b64encode(buffered.getvalue()).decode()

        try:
            logger.info(f"배경 제거 중... (모델: {model.model_name})")
            
            # TODO: 실제 배경 제거 로직 구현
            result = await self._execute_with_model(model, image=image_base64, task="background_removal")
            return Image.open(io.BytesIO(base64.b64decode(result["image_data"])))
            
        except Exception as e:
            logger.error(f"배경 제거 실패: {str(e)}")
            return None
    
    def _add_watermark(self, image: Image.Image) -> Image.Image:
        """워터마크 추가"""
        
        try:
            # 이미지 복사
            watermarked = image.copy()
            
            # RGBA 모드로 변환
            if watermarked.mode != 'RGBA':
                watermarked = watermarked.convert('RGBA')
            
            # 워터마크 레이어 생성
            txt_layer = Image.new('RGBA', watermarked.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)
            
            # 폰트 설정 (시스템 기본 폰트 사용)
            try:
                # 폰트 크기는 이미지 크기에 비례
                font_size = max(20, min(watermarked.width, watermarked.height) // 20)
                # 시스템 폰트 경로를 직접 지정하거나, font_path를 설정 파일에서 가져오도록 변경
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" # 예시 경로, 실제 환경에 맞게 변경 필요
                font = ImageFont.truetype(font_path, font_size)
            except Exception:
                font = ImageFont.load_default()
            
            # 텍스트 크기 계산
            bbox = draw.textbbox((0, 0), self.watermark_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # 우측 하단에 위치
            margin = 20
            x = watermarked.width - text_width - margin
            y = watermarked.height - text_height - margin
            
            # 워터마크 그리기
            draw.text(
                (x, y), 
                self.watermark_text, 
                fill=(255, 255, 255, self.watermark_opacity),
                font=font
            )
            
            # 레이어 합성
            watermarked = Image.alpha_composite(watermarked, txt_layer)
            
            logger.info("워터마크 추가 완료")
            return watermarked
            
        except Exception as e:
            logger.error(f"워터마크 추가 실패: {str(e)}")
            return image
    
    def _save_image(
        self,
        image: Image.Image,
        suffix: str,
        format: str,
        quality: int
    ) -> Path:
        """이미지 저장"""
        
        # 파일명 생성 (해시 기반)
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="PNG")
        image_hash = hashlib.md5(image_bytes.getvalue()).hexdigest()[:8]
        
        filename = f"{image_hash}_{suffix}.{format.lower()}"
        output_path = self.output_dir / filename
        
        # 저장 옵션
        save_kwargs = {}
        if format.lower() in ["jpg", "jpeg"]:
            save_kwargs["format"] = "JPEG"
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True
            # RGBA를 RGB로 변환
            if image.mode == 'RGBA':
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[3])
                image = rgb_image
        elif format.lower() == "png":
            save_kwargs["format"] = "PNG"
            save_kwargs["optimize"] = True
        elif format.lower() == "webp":
            save_kwargs["format"] = "WEBP"
            save_kwargs["quality"] = quality
            save_kwargs["method"] = 6
        else:
            save_kwargs["format"] = format.upper()
        
        # 저장
        image.save(output_path, **save_kwargs)
        logger.info(f"이미지 저장: {output_path}")
        
        return output_path
    
    async def process_batch_images(
        self,
        image_paths: List[Union[str, Path]],
        task_config: Optional[TaskConfig] = None,
        max_concurrent: int = 3,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """여러 이미지 배치 처리"""
        
        logger.info(f"{len(image_paths)}개 이미지 배치 처리 시작")
        
        results = await self.process_batch(
            image_paths,
            task_config,
            max_concurrent,
            **kwargs
        )
        
        logger.info(
            f"배치 처리 완료: 성공 {len(results)}, "
            f"실패 {len(image_paths) - len(results)}"
        )
        
        return results
    
    def cleanup_processed_images(self, days: int = 7):
        """오래된 처리 이미지 정리"""
        
        import time
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 60 * 60)
        
        removed_count = 0
        for file_path in self.output_dir.iterdir():
            if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                file_path.unlink()
                removed_count += 1
        
        logger.info(f"{days}일 이상 된 이미지 {removed_count}개 삭제")
        return removed_count