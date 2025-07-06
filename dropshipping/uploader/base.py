import abc
from enum import Enum
from typing import Dict, Any

from pydantic_settings import BaseSettings

from dropshipping.models.product import StandardProduct
from dropshipping.storage.base import BaseStorage
from dropshipping.config import settings, Settings

class MarketplaceType(str, Enum):
    COUPANG = "coupang"
    ELEVENST = "elevenst"
    SMARTSTORE = "smartstore"
    GMARKET = "gmarket"
    AUCTION = "auction"

class UploadStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class BaseUploader(abc.ABC):
    """
    모든 마켓플레이스 업로더의 추상 기본 클래스.
    상품 업로드, 재고 업데이트, 가격 업데이트 등의 공통 인터페이스를 정의합니다.
    """

    def __init__(self, marketplace_type: MarketplaceType, storage: BaseStorage, config: BaseSettings):
        self.marketplace_type = marketplace_type
        self.storage = storage
        self.config = config

    @abc.abstractmethod
    def upload_product(self, product: StandardProduct) -> Dict[str, Any]:
        """
        상품을 마켓플레이스에 업로드합니다.
        성공 시 마켓플레이스 상품 ID, URL 등 정보를 반환합니다.
        """
        pass

    @abc.abstractmethod
    def update_stock(self, marketplace_product_id: str, stock: int) -> bool:
        """
        마켓플레이스에 등록된 상품의 재고를 업데이트합니다.
        """
        pass

    @abc.abstractmethod
    def update_price(self, marketplace_product_id: str, price: float) -> bool:
        """
        마켓플레이스에 등록된 상품의 가격을 업데이트합니다.
        """
        pass

    @abc.abstractmethod
    def check_upload_status(self, upload_id: str) -> Dict[str, Any]:
        """
        상품 업로드 상태를 확인합니다.
        """
        pass