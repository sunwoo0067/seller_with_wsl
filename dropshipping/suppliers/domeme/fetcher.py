import json
from typing import Dict, List, Optional

import requests

from ..base.base_fetcher import BaseFetcher


class DomemeFetcher(BaseFetcher):
    def __init__(self, storage, supplier_name, api_key, api_url, **kwargs):
        super().__init__(storage, supplier_name)
        self.api_key = api_key
        self.api_url = api_url
        self.page_size = kwargs.get("page_size", 100)
        self.timeout = kwargs.get("timeout", 30)

    def run_incremental(self, **kwargs) -> int:
        # TODO: 카테고리 기반 전체 수집 로직 구현 필요
        return super().run_incremental(**kwargs)

    def fetch_list(self, page: int = 1) -> Optional[bytes]:
        """
        도매매 상품 목록을 페이지별로 가져옵니다.
        """
        endpoint = "/api/rest/product/searchProductList"
        params = {
            "ver": "4.1",
            "start": page,
            "limit": self.page_size,
            "market": "supply",
            "aid": self.api_key,
            "ca": "01_11_00_00_00",  # API 필수 필터 (임시 카테고리)
            "om": "json",  # 응답 형식을 JSON으로 지정
        }

        print(f"Fetching list page {page} for supplier {self.supplier_name}...")
        return self._call_api(endpoint, params)

    def fetch_detail(self, item_id: str) -> Optional[bytes]:
        """
        도매매 단일 상품의 상세 정보를 가져옵니다.
        """
        endpoint = "/api/rest/product/searchProductInfo"
        params = {
            "ver": "4.5",
            "productNo": item_id,
            "market": "supply",
            "aid": self.api_key,
            "om": "json",
        }
        return self._call_api(endpoint, params)

    def _call_api(self, endpoint: str, params: Dict) -> Optional[bytes]:
        full_url = f"{self.api_url}{endpoint}"
        try:
            response = requests.get(full_url, params=params, timeout=self.timeout)
            response.raise_for_status()  # HTTP 에러 발생 시 예외 발생
            return response.content
        except requests.exceptions.RequestException as e:
            print(f"API 호출 에러 ({endpoint}): {e}")
            return None

    def _process_list_response(self, response_content: bytes) -> List[Dict]:
        items = []
        try:
            data = json.loads(response_content)
            if data.get("response", {}).get("result", {}).get("code") != "00":
                msg = data.get("response", {}).get("result", {}).get("msg")
                print(f"API 응답 에러: {msg}")
                return items

            item_list = data.get("response", {}).get("itemList", {}).get("item", [])
            if isinstance(item_list, dict):
                item_list = [item_list]

            for item_data in item_list:
                items.append(
                    {
                        "id": item_data.get("no"),
                        "name": item_data.get("name"),
                        "price": item_data.get("price"),
                        "stock": item_data.get("stock"),
                        "image_url": item_data.get("imageUrl"),
                        "reg_date": item_data.get("regDate"),
                    }
                )
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 에러: {e} - 응답: {response_content[:200]}")
        return items

    def _process_detail_response(
        self, response_content: bytes, item_id: str
    ) -> Optional[Dict]:
        try:
            data = json.loads(response_content)
            if data.get("response", {}).get("result", {}).get("code") != "00":
                msg = data.get("response", {}).get("result", {}).get("msg")
                print(f"API 응답 에러 (detail): {msg}")
                return None

            item_info = data.get("response", {}).get("item", {})
            return {
                "id": item_id,
                "description": item_info.get("description"),
                "options": item_info.get("options"),
                "shipping_fee": item_info.get("shippingFee"),
            }
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 에러 (detail): {e} - 응답: {response_content[:200]}")
            return None