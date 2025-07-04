"""
데이터 변환 기본 인터페이스
각 공급사/마켓플레이스별 변환기의 기반 클래스
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, TypeVar, Generic
from datetime import datetime

from dropshipping.models.product import StandardProduct
from loguru import logger


T = TypeVar("T")  # 원본 데이터 타입


class TransformError(Exception):
    """변환 중 발생하는 오류"""

    pass


class BaseTransformer(ABC, Generic[T]):
    """
    기본 변환기 추상 클래스
    원본 데이터를 StandardProduct로 변환하거나 그 반대로 변환
    """

    def __init__(self, supplier_id: str):
        self.supplier_id = supplier_id
        self._errors: List[Dict[str, Any]] = []

    @abstractmethod
    def to_standard(self, raw_data: T) -> StandardProduct:
        """
        원본 데이터를 표준 형식으로 변환

        Args:
            raw_data: 공급사별 원본 데이터

        Returns:
            StandardProduct: 표준화된 상품 데이터

        Raises:
            TransformError: 변환 실패시
        """
        pass

    @abstractmethod
    def from_standard(self, product: StandardProduct) -> T:
        """
        표준 형식을 원본 데이터 형식으로 변환
        (마켓플레이스 업로드용)

        Args:
            product: 표준 상품 데이터

        Returns:
            원본 형식의 데이터

        Raises:
            TransformError: 변환 실패시
        """
        pass

    def validate_raw_data(self, raw_data: T) -> bool:
        """
        원본 데이터 유효성 검증

        Args:
            raw_data: 검증할 원본 데이터

        Returns:
            bool: 유효성 여부
        """
        return raw_data is not None

    def preprocess(self, raw_data: T) -> T:
        """
        변환 전 전처리 (선택적 구현)

        Args:
            raw_data: 전처리할 원본 데이터

        Returns:
            전처리된 데이터
        """
        return raw_data

    def postprocess(self, product: StandardProduct) -> StandardProduct:
        """
        변환 후 후처리 (선택적 구현)

        Args:
            product: 후처리할 표준 상품

        Returns:
            후처리된 표준 상품
        """
        return product

    def transform(self, raw_data: T) -> Optional[StandardProduct]:
        """
        전체 변환 파이프라인 실행

        Args:
            raw_data: 변환할 원본 데이터

        Returns:
            Optional[StandardProduct]: 변환된 상품 또는 None
        """
        try:
            # 1. 유효성 검증
            if not self.validate_raw_data(raw_data):
                self._log_error("유효하지 않은 원본 데이터", raw_data)
                return None

            # 2. 전처리
            preprocessed = self.preprocess(raw_data)

            # 3. 변환
            product = self.to_standard(preprocessed)

            # 4. 후처리
            final_product = self.postprocess(product)

            logger.debug(f"상품 변환 성공: {final_product.id}")
            return final_product

        except TransformError as e:
            self._log_error(f"변환 오류: {str(e)}", raw_data)
            return None
        except Exception as e:
            self._log_error(f"예기치 않은 오류: {str(e)}", raw_data)
            return None

    def batch_transform(self, raw_data_list: List[T]) -> List[StandardProduct]:
        """
        배치 변환

        Args:
            raw_data_list: 원본 데이터 목록

        Returns:
            List[StandardProduct]: 변환된 상품 목록
        """
        results = []
        for raw_data in raw_data_list:
            product = self.transform(raw_data)
            if product:
                results.append(product)

        logger.info(f"배치 변환 완료: {len(results)}/{len(raw_data_list)} 성공")
        return results

    def _log_error(self, message: str, raw_data: Any):
        """오류 로깅"""
        error = {
            "timestamp": datetime.now(),
            "supplier_id": self.supplier_id,
            "message": message,
            "raw_data": raw_data,
        }
        self._errors.append(error)
        logger.error(f"[{self.supplier_id}] {message}")

    @property
    def errors(self) -> List[Dict[str, Any]]:
        """발생한 오류 목록"""
        return self._errors

    def clear_errors(self):
        """오류 목록 초기화"""
        self._errors.clear()


class DictTransformer(BaseTransformer[Dict[str, Any]]):
    """
    딕셔너리 형태의 원본 데이터를 다루는 변환기
    대부분의 JSON/XML API 응답에 사용
    """

    def get_value(self, data: Dict[str, Any], path: str, default: Any = None) -> Any:
        """
        점 표기법으로 중첩된 딕셔너리 값 추출

        Args:
            data: 데이터 딕셔너리
            path: 점으로 구분된 경로 (예: "product.price.value")
            default: 기본값

        Returns:
            추출된 값 또는 기본값
        """
        keys = path.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def safe_int(self, value: Any, default: int = 0) -> int:
        """안전한 정수 변환"""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def safe_float(self, value: Any, default: float = 0.0) -> float:
        """안전한 실수 변환"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def safe_str(self, value: Any, default: str = "") -> str:
        """안전한 문자열 변환"""
        if value is None:
            return default
        return str(value).strip()
