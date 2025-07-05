"""
도매매 API 클라이언트
requests 라이브러리를 사용하여 API와 통신
"""

from typing import Any, Dict, Optional

import requests
from loguru import logger

from dropshipping.config import settings


class DomemeAPIError(Exception):
    """도매매 API 오류"""

    pass


class DomemeClient:
    """도매매 API 클라이언트"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or (settings.domeme.api_key if settings.domeme else None)
        if not self.api_key:
            raise ValueError("도매매 API 키가 필요합니다.")
        self.base_url = "https://openapi.domeggook.com"

    def check_connection(self) -> bool:
        """API 연결 상태 확인"""
        try:
            # 간단한 상품 목록 조회를 시도하여 연결 확인
            self.search_products(start_row=1, end_row=1)
            return True
        except DomemeAPIError as e:
            logger.error(f"도매매 API 연결 실패: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"예기치 않은 오류로 도매매 API 연결 실패: {str(e)}")
            return False

    def _request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """API 요청 공통 메서드"""
        url = f"{self.base_url}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        params["aid"] = self.api_key

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()  # 2xx 이외의 상태 코드에 대해 예외 발생

            data = response.json()

            # API 에러 처리
            if data.get("resultCode") != "00":
                error_code = data.get("resultCode")
                error_message = data.get("message", "알 수 없는 오류")
                raise DomemeAPIError(f"API Error {error_code}: {error_message}")

            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"도매매 API 요청 실패: {str(e)}")
            raise DomemeAPIError(f"API 요청 실패: {str(e)}") from e

    def search_products(self, **kwargs) -> Dict[str, Any]:
        """상품 목록 검색"""
        endpoint = "api/rest/product/searchProductList"

        # API 파라미터 준비
        params = {
            "market": "supply",  # 공급 상품
            "startRow": kwargs.get("start_row", 1),
            "endRow": kwargs.get("end_row", 100),
            "orderBy": kwargs.get("order_by", "modDate"),
            "sortType": kwargs.get("sort_type", "desc"),
            "ver": "4.1",
        }
        if "categoryCode" in kwargs:
            params["categoryCode"] = kwargs["categoryCode"]

        data = self._request(endpoint, params)

        # 결과 파싱
        products = data.get("product", [])
        total_count = int(data.get("totalCount", 0))
        has_next = kwargs.get("end_row", 100) < total_count

        return {"products": products, "total_count": total_count, "has_next": has_next}

    def get_product_detail(self, product_id: str) -> Dict[str, Any]:
        """상품 상세 정보 조회"""
        endpoint = "api/rest/product/searchProductInfo"
        params = {"productNo": product_id, "ver": "4.5", "market": "supply"}

        data = self._request(endpoint, params)

        return data.get("product", {})
