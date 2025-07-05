"""
저장소 기본 인터페이스
DB, 파일 등 다양한 저장소 구현을 위한 추상 클래스
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from dropshipping.models.product import StandardProduct


class BaseStorage(ABC):
    """저장소 추상 클래스"""

    @abstractmethod
    def save_raw_product(self, raw_data: Dict[str, Any]) -> str:
        """
        원본 상품 데이터 저장

        Args:
            raw_data: 원본 데이터 (supplier_id, data_hash, raw_json 등 포함)

        Returns:
            저장된 레코드 ID
        """
        pass

    @abstractmethod
    def save_processed_product(self, raw_id: str, product: StandardProduct) -> str:
        """
        처리된 상품 데이터 저장

        Args:
            raw_id: 원본 데이터 ID
            product: 표준화된 상품 데이터

        Returns:
            저장된 레코드 ID
        """
        pass

    @abstractmethod
    def exists_by_hash(self, supplier_id: str, data_hash: str) -> bool:
        """
        해시로 중복 체크

        Args:
            supplier_id: 공급사 ID
            data_hash: 데이터 해시

        Returns:
            존재 여부
        """
        pass

    @abstractmethod
    def get_raw_product(self, record_id: str) -> Optional[Dict[str, Any]]:
        """
        원본 상품 데이터 조회

        Args:
            record_id: 레코드 ID

        Returns:
            원본 데이터 또는 None
        """
        pass

    @abstractmethod
    def get_processed_product(self, record_id: str) -> Optional[StandardProduct]:
        """
        처리된 상품 데이터 조회

        Args:
            record_id: 레코드 ID

        Returns:
            표준 상품 데이터 또는 None
        """
        pass

    @abstractmethod
    def list_raw_products(
        self,
        supplier_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        원본 상품 목록 조회

        Args:
            supplier_id: 공급사 ID (None이면 전체)
            status: 상태 필터
            limit: 조회 개수
            offset: 시작 위치

        Returns:
            원본 데이터 목록
        """
        pass

    @abstractmethod
    def update_status(self, record_id: str, status: str) -> bool:
        """
        상태 업데이트

        Args:
            record_id: 레코드 ID
            status: 새로운 상태

        Returns:
            성공 여부
        """
        pass

    @abstractmethod
    def get_stats(self, supplier_id: Optional[str] = None) -> Dict[str, Any]:
        """
        통계 조회

        Args:
            supplier_id: 공급사 ID (None이면 전체)

        Returns:
            통계 정보
        """
        pass

    @abstractmethod
    async def upsert(
        self, table_name: str, records: List[Dict[str, Any]], on_conflict: str
    ) -> List[Dict[str, Any]]:
        """레코드를 삽입하거나 업데이트합니다."""
        pass

    @abstractmethod
    def get_marketplace_upload(self, product_id: str, marketplace: str) -> Optional[Dict[str, Any]]:
        """마켓플레이스 업로드 기록을 조회합니다."""
        pass

    @abstractmethod
    def save_marketplace_upload(self, record: Dict[str, Any]):
        """마켓플레이스 업로드 기록을 저장합니다."""
        pass

    @abstractmethod
    def get_pricing_rules(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """가격 책정 규칙을 조회합니다."""
        pass

    @abstractmethod
    def get_all_category_mappings(self) -> List[Dict[str, Any]]:
        """모든 카테고리 매핑 정보를 조회합니다."""
        pass

    @abstractmethod
    def get_supplier_code(self, supplier_id: str) -> str:
        """공급사 ID로 코드를 조회합니다."""
        pass

    @abstractmethod
    def get_marketplace_code(self, marketplace_id: str) -> str:
        """마켓플레이스 ID로 코드를 조회합니다."""
        pass
