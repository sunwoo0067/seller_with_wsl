"""
마켓플레이스 업로더 기본 클래스
모든 마켓플레이스 업로더의 추상 기반 클래스
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal
from enum import Enum
import asyncio

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from dropshipping.models.product import StandardProduct
from dropshipping.storage.base import BaseStorage


class UploadStatus(Enum):
    """업로드 상태"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"  # 일부만 성공


class MarketplaceType(Enum):
    """마켓플레이스 타입"""
    COUPANG = "coupang"
    ELEVENST = "11st"
    NAVER = "naver"
    GMARKET = "gmarket"
    AUCTION = "auction"
    INTERPARK = "interpark"


class BaseUploader(ABC):
    """마켓플레이스 업로더 기본 클래스"""
    
    def __init__(
        self,
        marketplace: MarketplaceType,
        storage: BaseStorage,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        초기화
        
        Args:
            marketplace: 마켓플레이스 타입
            storage: 저장소 인스턴스
            config: 업로더 설정
        """
        self.marketplace = marketplace
        self.storage = storage
        self.config = config or {}
        
        # API 설정
        self.api_key = self.config.get("api_key")
        self.api_secret = self.config.get("api_secret")
        self.seller_id = self.config.get("seller_id")
        
        # 업로드 설정
        self.batch_size = self.config.get("batch_size", 10)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 5)
        
        # 통계
        self.stats = {
            "uploaded": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }
    
    @abstractmethod
    async def validate_product(self, product: StandardProduct) -> Tuple[bool, Optional[str]]:
        """
        상품 검증
        
        Args:
            product: 검증할 상품
            
        Returns:
            (유효 여부, 오류 메시지)
        """
        pass
    
    @abstractmethod
    async def transform_product(self, product: StandardProduct) -> Dict[str, Any]:
        """
        상품 데이터 변환
        
        Args:
            product: 변환할 상품
            
        Returns:
            마켓플레이스 형식의 상품 데이터
        """
        pass
    
    @abstractmethod
    async def upload_single(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        단일 상품 업로드
        
        Args:
            product_data: 마켓플레이스 형식의 상품 데이터
            
        Returns:
            업로드 결과
        """
        pass
    
    @abstractmethod
    async def update_single(
        self,
        marketplace_product_id: str,
        product_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        단일 상품 수정
        
        Args:
            marketplace_product_id: 마켓플레이스 상품 ID
            product_data: 수정할 상품 데이터
            
        Returns:
            수정 결과
        """
        pass
    
    @abstractmethod
    async def check_product_status(self, marketplace_product_id: str) -> Dict[str, Any]:
        """
        상품 상태 확인
        
        Args:
            marketplace_product_id: 마켓플레이스 상품 ID
            
        Returns:
            상품 상태 정보
        """
        pass
    
    async def upload_product(
        self,
        product: StandardProduct,
        update_existing: bool = True
    ) -> Dict[str, Any]:
        """
        상품 업로드 (신규 또는 수정)
        
        Args:
            product: 업로드할 상품
            update_existing: 기존 상품 수정 여부
            
        Returns:
            업로드 결과
        """
        result = {
            "product_id": product.id,
            "status": UploadStatus.PENDING,
            "marketplace": self.marketplace.value,
            "marketplace_product_id": None,
            "errors": [],
            "uploaded_at": None
        }
        
        try:
            # 1. 상품 검증
            is_valid, error_msg = await self.validate_product(product)
            if not is_valid:
                result["status"] = UploadStatus.FAILED
                result["errors"].append(f"검증 실패: {error_msg}")
                self.stats["failed"] += 1
                return result
            
            # 2. 기존 업로드 확인
            existing = await self._check_existing_upload(product.id)
            
            # 3. 상품 변환
            product_data = await self.transform_product(product)
            
            # 4. 업로드 또는 수정
            if existing and update_existing:
                # 기존 상품 수정
                upload_result = await self.update_single(
                    existing["marketplace_product_id"],
                    product_data
                )
                result["marketplace_product_id"] = existing["marketplace_product_id"]
                logger.info(f"상품 수정: {product.id} -> {existing['marketplace_product_id']}")
            else:
                # 신규 업로드
                upload_result = await self.upload_single(product_data)
                result["marketplace_product_id"] = upload_result.get("product_id")
                logger.info(f"신규 업로드: {product.id} -> {result['marketplace_product_id']}")
            
            # 5. 결과 처리
            if upload_result.get("success"):
                result["status"] = UploadStatus.SUCCESS
                result["uploaded_at"] = datetime.now()
                self.stats["uploaded"] += 1
                
                # 업로드 기록 저장
                await self._save_upload_record(product, result)
            else:
                result["status"] = UploadStatus.FAILED
                result["errors"].append(upload_result.get("error", "업로드 실패"))
                self.stats["failed"] += 1
            
        except Exception as e:
            logger.error(f"상품 업로드 오류: {product.id} - {str(e)}")
            result["status"] = UploadStatus.FAILED
            result["errors"].append(str(e))
            self.stats["failed"] += 1
            self.stats["errors"].append({
                "product_id": product.id,
                "error": str(e),
                "timestamp": datetime.now()
            })
        
        return result
    
    async def upload_batch(
        self,
        products: List[StandardProduct],
        update_existing: bool = True,
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        배치 업로드
        
        Args:
            products: 업로드할 상품 목록
            update_existing: 기존 상품 수정 여부
            max_concurrent: 최대 동시 업로드 수
            
        Returns:
            업로드 결과 목록
        """
        logger.info(
            f"{self.marketplace.value}에 {len(products)}개 상품 배치 업로드 시작"
        )
        
        # 세마포어로 동시 업로드 제한
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def upload_with_semaphore(product):
            async with semaphore:
                return await self.upload_product(product, update_existing)
        
        # 동시 업로드
        results = await asyncio.gather(
            *[upload_with_semaphore(product) for product in products],
            return_exceptions=True
        )
        
        # 결과 처리
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"배치 업로드 오류: {products[i].id} - {str(result)}")
                valid_results.append({
                    "product_id": products[i].id,
                    "status": UploadStatus.FAILED,
                    "errors": [str(result)]
                })
            else:
                valid_results.append(result)
        
        # 통계 로그
        success_count = sum(1 for r in valid_results if r["status"] == UploadStatus.SUCCESS)
        logger.info(
            f"배치 업로드 완료: 성공 {success_count}, "
            f"실패 {len(valid_results) - success_count}"
        )
        
        return valid_results
    
    async def _check_existing_upload(self, product_id: str) -> Optional[Dict[str, Any]]:
        """기존 업로드 확인"""
        try:
            # 실제로는 storage에서 조회
            # return await self.storage.get_marketplace_upload(
            #     product_id, self.marketplace.value
            # )
            return None
        except Exception as e:
            logger.error(f"기존 업로드 확인 오류: {str(e)}")
            return None
    
    async def _save_upload_record(
        self,
        product: StandardProduct,
        result: Dict[str, Any]
    ):
        """업로드 기록 저장"""
        try:
            # 실제로는 storage에 저장
            # await self.storage.save_marketplace_upload({
            #     "product_id": product.id,
            #     "marketplace": self.marketplace.value,
            #     "marketplace_product_id": result["marketplace_product_id"],
            #     "status": result["status"].value,
            #     "uploaded_at": result["uploaded_at"],
            #     "product_data": product.dict()
            # })
            logger.info(f"업로드 기록 저장: {product.id}")
        except Exception as e:
            logger.error(f"업로드 기록 저장 오류: {str(e)}")
    
    def validate_api_credentials(self) -> bool:
        """API 자격증명 검증"""
        if self.marketplace in [MarketplaceType.COUPANG, MarketplaceType.ELEVENST]:
            return bool(self.api_key and self.api_secret)
        elif self.marketplace == MarketplaceType.NAVER:
            return bool(self.api_key and self.api_secret and self.seller_id)
        return True  # Excel 업로더는 API 불필요
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 조회"""
        total = self.stats["uploaded"] + self.stats["failed"] + self.stats["skipped"]
        
        return {
            **self.stats,
            "total": total,
            "success_rate": (
                self.stats["uploaded"] / total if total > 0 else 0
            ),
            "marketplace": self.marketplace.value
        }
    
    def reset_stats(self):
        """통계 초기화"""
        self.stats = {
            "uploaded": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(5),
        retry=retry_if_exception_type(Exception)
    )
    async def _api_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """API 요청 (재시도 포함)"""
        # 구체적인 구현은 각 업로더에서
        raise NotImplementedError