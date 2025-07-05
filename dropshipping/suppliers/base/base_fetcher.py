"""
공급사 데이터 수집기 기본 추상 클래스
모든 공급사별 Fetcher가 상속받아 구현
"""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# tenacity 대신 수동 재시도 구현
from dropshipping.transformers.base import BaseTransformer


class FetchError(Exception):
    """데이터 수집 중 발생하는 오류"""

    pass


class BaseFetcher(ABC):
    """
    공급사 데이터 수집기 추상 클래스

    각 공급사별로 이 클래스를 상속받아 구현
    - fetch_list: 상품 목록 조회
    - fetch_detail: 상품 상세 조회
    - 중복 체크, 재시도, 로깅 등 공통 기능 제공
    """

    def __init__(
        self, supplier_id: str, storage=None, transformer: Optional[BaseTransformer] = None
    ):
        """
        Args:
            supplier_id: 공급사 식별자
            storage: 저장소 인스턴스 (DB 또는 파일)
            transformer: 데이터 변환기
        """
        self.supplier_id = supplier_id
        self.storage = storage
        self.transformer = transformer
        self._stats = {"fetched": 0, "duplicates": 0, "errors": 0, "saved": 0}

    @abstractmethod
    def fetch_list(self, page: int = 1, **kwargs) -> Tuple[List[Dict[str, Any]], bool]:
        """
        상품 목록 조회

        Args:
            page: 페이지 번호
            **kwargs: 추가 파라미터 (날짜, 카테고리 등)

        Returns:
            Tuple[상품 목록, 다음 페이지 존재 여부]

        Raises:
            FetchError: 조회 실패시
        """
        pass

    @abstractmethod
    def fetch_detail(self, product_id: str) -> Dict[str, Any]:
        """
        상품 상세 정보 조회

        Args:
            product_id: 상품 ID

        Returns:
            상품 상세 정보

        Raises:
            FetchError: 조회 실패시
        """
        pass

    def fetch_with_retry(self, fetch_func, *args, **kwargs):
        """재시도 로직이 포함된 fetch 실행"""
        max_retries = 3
        retry_count = 0
        wait_time = 4  # 초기 대기 시간

        while retry_count < max_retries:
            try:
                return fetch_func(*args, **kwargs)
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"Fetch 최종 실패 (시도 {retry_count}/{max_retries}): {str(e)}")
                    raise FetchError(f"Fetch 실패: {str(e)}")

                logger.warning(f"Fetch 실패 (시도 {retry_count}/{max_retries}): {str(e)}")
                import time

                time.sleep(wait_time)
                wait_time = min(wait_time * 2, 10)  # 지수 백오프, 최대 10초

    def calculate_hash(self, data: Dict[str, Any]) -> str:
        """
        데이터 해시 계산 (중복 체크용)

        Args:
            data: 원본 데이터

        Returns:
            SHA256 해시 문자열
        """
        # 정렬된 JSON 문자열로 변환하여 일관된 해시 생성
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def is_duplicate(self, data_hash: str) -> bool:
        """
        중복 데이터 체크

        Args:
            data_hash: 데이터 해시

        Returns:
            중복 여부
        """
        if not self.storage:
            return False

        return self.storage.exists_by_hash(self.supplier_id, data_hash)

    def save_raw(self, data: Dict[str, Any]) -> Optional[str]:
        """
        원본 데이터 저장

        Args:
            data: 원본 데이터

        Returns:
            저장된 레코드 ID 또는 None
        """
        if not self.storage:
            logger.warning("저장소가 설정되지 않았습니다")
            return None

        # 해시 계산
        data_hash = self.calculate_hash(data)

        # 중복 체크
        if self.is_duplicate(data_hash):
            self._stats["duplicates"] += 1
            logger.debug(f"중복 데이터 스킵: {data.get('productNo', 'unknown')}")
            return None

        # 메타데이터 추가
        raw_record = {
            "supplier_id": self.supplier_id,
            "supplier_product_id": data.get("productNo", data.get("id", "unknown")),
            "data_hash": data_hash,
            "raw_json": data,
            "fetched_at": datetime.now(),
            "status": "fetched",
        }

        try:
            record_id = self.storage.save_raw_product(raw_record)
            self._stats["saved"] += 1
            return record_id
        except Exception as e:
            logger.error(f"데이터 저장 실패: {str(e)}")
            self._stats["errors"] += 1
            return None

    def run_incremental(self, since: Optional[datetime] = None, max_pages: int = 100):
        """
        증분 동기화 실행

        Args:
            since: 이 시점 이후의 데이터만 수집
            max_pages: 최대 페이지 수
        """
        logger.info(f"[{self.supplier_id}] 증분 동기화 시작")

        page = 1
        total_products = 0

        while page <= max_pages:
            try:
                # 목록 조회
                products, has_next = self.fetch_with_retry(self.fetch_list, page=page, since=since)

                if not products:
                    logger.info(f"더 이상 상품이 없습니다 (page={page})")
                    break

                self._stats["fetched"] += len(products)

                # 각 상품 처리
                for product in products:
                    try:
                        # 상세 정보가 필요한 경우 조회
                        if self.needs_detail_fetch(product):
                            product_id = self.extract_product_id(product)
                            detail = self.fetch_with_retry(self.fetch_detail, product_id)
                            product = self.merge_detail(product, detail)

                        # 원본 데이터 저장
                        record_id = self.save_raw(product)

                        # 변환 및 후처리
                        if record_id and self.transformer:
                            self.process_product(record_id, product)

                        total_products += 1

                    except Exception as e:
                        logger.error(f"상품 처리 실패: {str(e)}")
                        self._stats["errors"] += 1

                # 다음 페이지 확인
                if not has_next:
                    logger.info("마지막 페이지입니다")
                    break

                page += 1

            except FetchError as e:
                logger.error(f"페이지 {page} 수집 실패: {str(e)}")
                self._stats["errors"] += 1
                break
            except Exception as e:
                logger.error(f"예기치 않은 오류: {str(e)}")
                self._stats["errors"] += 1
                break

        # 통계 출력
        logger.info(
            f"[{self.supplier_id}] 동기화 완료: "
            f"수집={self._stats['fetched']}, "
            f"저장={self._stats['saved']}, "
            f"중복={self._stats['duplicates']}, "
            f"오류={self._stats['errors']}"
        )

    def needs_detail_fetch(self, list_item: Dict[str, Any]) -> bool:
        """
        상세 정보 조회가 필요한지 판단

        기본적으로 False, 필요시 하위 클래스에서 재정의
        """
        return False

    def extract_product_id(self, product: Dict[str, Any]) -> str:
        """
        상품 ID 추출

        하위 클래스에서 필요시 재정의
        """
        return product.get("productNo", product.get("id", ""))

    def merge_detail(self, list_item: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
        """
        목록 데이터와 상세 데이터 병합

        하위 클래스에서 필요시 재정의
        """
        list_item.update(detail)
        return list_item

    def process_product(self, record_id: str, raw_data: Dict[str, Any]):
        """
        상품 데이터 후처리 (변환, 검증 등)

        하위 클래스에서 필요시 재정의
        """
        if self.transformer:
            try:
                standard_product = self.transformer.to_standard(raw_data)
                if standard_product and self.storage:
                    self.storage.save_processed_product(record_id, standard_product)
            except Exception as e:
                logger.error(f"상품 변환 실패: {str(e)}")

    @property
    def stats(self) -> Dict[str, int]:
        """수집 통계 반환"""
        return self._stats.copy()

    def reset_stats(self):
        """통계 초기화"""
        self._stats = {"fetched": 0, "duplicates": 0, "errors": 0, "saved": 0}
