"""
도매매(Domeme) API 클라이언트
XML 기반 REST API 통신
"""

import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode
import time

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from dropshipping.config import settings


class DomemeAPIError(Exception):
    """도매매 API 오류"""

    pass


class DomemeClient:
    """도매매 API 클라이언트"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: 도매매 API 키 (없으면 설정에서 로드)
        """
        self.api_key = api_key or (settings.domeme.api_key if settings.domeme else None)
        if not self.api_key:
            raise ValueError("도매매 API 키가 설정되지 않았습니다")

        self.base_url = (
            settings.domeme.api_url
            if settings.domeme
            else "https://api.domeggook.com/open/v4.1/search/searchProductList.do"
        )

        # 세션 생성
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "DropshippingAutomation/1.0",
                "Accept": "application/xml",
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )

        # Rate limiting
        self._last_request_time = 0
        self._min_request_interval = 0.5  # 초당 최대 2회

    def _ensure_rate_limit(self):
        """Rate limiting 확인"""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < self._min_request_interval:
            sleep_time = self._min_request_interval - time_since_last
            logger.debug(f"Rate limit: {sleep_time:.2f}초 대기")
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, DomemeAPIError)),
    )
    def _request(self, params: Dict[str, Any]) -> ET.Element:
        """
        API 요청 실행

        Args:
            params: 요청 파라미터

        Returns:
            XML 응답 루트 요소

        Raises:
            DomemeAPIError: API 오류시
        """
        # Rate limiting
        self._ensure_rate_limit()

        # API 키 추가
        params["apiKey"] = self.api_key

        try:
            logger.debug(f"도매매 API 요청: {params}")
            response = self.session.post(self.base_url, data=params, timeout=30)
            response.raise_for_status()

            # XML 파싱
            root = ET.fromstring(response.content)

            # 오류 체크
            error_code = root.find(".//errorCode")
            if error_code is not None and error_code.text != "000":
                error_msg = root.find(".//errorMsg")
                msg = error_msg.text if error_msg is not None else "알 수 없는 오류"
                raise DomemeAPIError(f"API 오류 ({error_code.text}): {msg}")

            return root

        except requests.RequestException as e:
            logger.error(f"API 요청 실패: {str(e)}")
            raise DomemeAPIError(f"네트워크 오류: {str(e)}")
        except ET.ParseError as e:
            logger.error(f"XML 파싱 실패: {str(e)}")
            raise DomemeAPIError(f"응답 파싱 오류: {str(e)}")

    def search_products(
        self,
        category_code: Optional[str] = None,
        keyword: Optional[str] = None,
        start_row: int = 1,
        end_row: int = 100,
        order_by: str = "regDate",
        sort_type: str = "desc",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        상품 검색

        Args:
            category_code: 카테고리 코드
            keyword: 검색 키워드
            start_row: 시작 행 (1부터)
            end_row: 종료 행
            order_by: 정렬 기준 (regDate, price, etc.)
            sort_type: 정렬 방향 (asc, desc)
            **kwargs: 추가 검색 조건

        Returns:
            검색 결과 딕셔너리
        """
        params = {
            "startRow": start_row,
            "endRow": end_row,
            "orderBy": order_by,
            "sortType": sort_type,
        }

        # 선택적 파라미터
        if category_code:
            params["categoryCode"] = category_code
        if keyword:
            params["keyword"] = keyword

        # 추가 검색 조건
        params.update(kwargs)

        # API 요청
        root = self._request(params)

        # 결과 파싱
        result = {"total_count": 0, "products": [], "has_next": False}

        # 전체 개수
        total_count = root.find(".//totalCount")
        if total_count is not None:
            result["total_count"] = int(total_count.text or 0)

        # 상품 목록
        products = root.findall(".//product")
        for product in products:
            product_dict = self._parse_product_element(product)
            result["products"].append(product_dict)

        # 다음 페이지 여부
        result["has_next"] = end_row < result["total_count"]

        logger.info(
            f"상품 검색 완료: 총 {result['total_count']}개 중 " f"{len(result['products'])}개 조회"
        )

        return result

    def get_product_detail(self, product_no: str) -> Dict[str, Any]:
        """
        상품 상세 조회

        Args:
            product_no: 상품 번호

        Returns:
            상품 상세 정보
        """
        params = {"productNo": product_no}

        # API 요청
        root = self._request(params)

        # 상품 정보 파싱
        product = root.find(".//product")
        if product is None:
            raise DomemeAPIError(f"상품을 찾을 수 없습니다: {product_no}")

        return self._parse_product_element(product)

    def _parse_product_element(self, element: ET.Element) -> Dict[str, Any]:
        """XML 상품 요소를 딕셔너리로 변환"""
        product = {}

        # 모든 하위 요소 처리
        for child in element:
            if child.text:
                # 숫자 필드 변환
                if child.tag in ["supplyPrice", "salePrice", "consumerPrice", "deliveryPrice"]:
                    try:
                        product[child.tag] = float(child.text)
                    except ValueError:
                        product[child.tag] = 0
                elif child.tag in ["stockQty"]:
                    try:
                        product[child.tag] = int(child.text)
                    except ValueError:
                        product[child.tag] = 0
                else:
                    product[child.tag] = child.text.strip()
            else:
                product[child.tag] = ""

        return product

    def get_categories(self, parent_code: Optional[str] = None) -> List[Dict[str, str]]:
        """
        카테고리 목록 조회

        Args:
            parent_code: 부모 카테고리 코드 (None이면 최상위)

        Returns:
            카테고리 목록
        """
        params = {"type": "category"}
        if parent_code:
            params["parentCode"] = parent_code

        # API 요청
        root = self._request(params)

        # 카테고리 파싱
        categories = []
        for category in root.findall(".//category"):
            cat_dict = {}
            for field in ["categoryCode", "categoryName", "level", "hasChild"]:
                elem = category.find(field)
                if elem is not None:
                    cat_dict[field] = elem.text

            if cat_dict:
                categories.append(cat_dict)

        return categories

    def check_connection(self) -> bool:
        """API 연결 테스트"""
        try:
            # 1개 상품만 조회해서 연결 테스트
            result = self.search_products(start_row=1, end_row=1)
            return result["total_count"] > 0
        except Exception as e:
            logger.error(f"API 연결 테스트 실패: {str(e)}")
            return False
