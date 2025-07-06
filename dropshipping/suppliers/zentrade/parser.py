"""
젠트레이드 응답 파서
XML/FTP 데이터를 표준 형식으로 파싱
"""

from typing import Any, Dict, List, Optional
from dropshipping.suppliers.base import BaseParser
from dropshipping.monitoring.logger import get_logger

logger = get_logger(__name__)


class ZentradeParser(BaseParser):
    """젠트레이드 XML 데이터 파서"""

    def parse_products(self, response: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """상품 목록 응답 파싱

        젠트레이드 fetcher는 이미 파싱된 딕셔너리 리스트를 반환하므로
        추가적인 가공만 수행

        Args:
            response: Fetcher에서 반환된 상품 목록

        Returns:
            파싱된 상품 목록
        """
        products = []

        for item in response:
            # 필수 필드 확인
            if not item.get("id") or not item.get("name"):
                logger.warning(f"필수 필드 누락: {item.get('id')}")
                continue

            product = self._normalize_product(item)
            if product:
                products.append(product)

        return products

    def parse_product_detail(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """상품 상세 응답 파싱

        Args:
            response: Fetcher에서 반환된 상품 상세 정보

        Returns:
            파싱된 상품 정보
        """
        if not response:
            return {}

        return self._normalize_product(response)

    def _normalize_product(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """상품 데이터 정규화

        Args:
            item: 원본 상품 데이터

        Returns:
            정규화된 상품 정보
        """
        try:
            # 옵션 정보 처리
            options = self._parse_options(item.get("options", []))

            # 재고 계산 (옵션별 재고 합계 또는 기본 재고)
            total_stock = item.get("stock", 0)
            if options and not total_stock:
                total_stock = sum(opt.get("stock", 0) for opt in options)

            # 배송 정보 처리
            shipping = item.get("shipping", {})
            shipping_fee = shipping.get("fee", 0) if shipping else 0
            shipping_method = shipping.get("method", "기본배송") if shipping else "기본배송"

            # 상태 정규화
            status = item.get("status", "active").lower()
            if status in ["active", "available", "판매중"]:
                status = "active"
            elif status in ["inactive", "unavailable", "판매중지"]:
                status = "inactive"
            elif status in ["soldout", "품절"]:
                status = "soldout"

            return {
                "id": item.get("id", ""),
                "name": item.get("name", "").strip(),
                "category": item.get("category", ""),
                "brand": item.get("brand", "").strip(),
                "model": item.get("model", "").strip(),
                "price": float(item.get("price", 0)),
                "stock": total_stock,
                "description": item.get("description", "").strip(),
                "status": status,
                "images": item.get("images", []),
                "options": options,
                "shipping_fee": shipping_fee,
                "shipping_method": shipping_method,
                "shipping_free_condition": shipping.get("free_condition", 0) if shipping else 0,
                "created_at": item.get("created_at", ""),
                "updated_at": item.get("updated_at", ""),
                # 원본 데이터 보존
                "raw_data": item,
            }

        except Exception as e:
            logger.error(f"상품 정규화 실패 [{item.get('id')}]: {str(e)}")
            return None

    def _parse_options(self, options: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """옵션 정보 파싱

        Args:
            options: 원본 옵션 목록

        Returns:
            파싱된 옵션 목록
        """
        parsed_options = []
        option_groups = {}

        for option in options:
            name = option.get("name", "")
            value = option.get("value", "")

            if not name or not value:
                continue

            # 옵션 그룹화 (같은 이름의 옵션들을 그룹으로)
            if name not in option_groups:
                option_groups[name] = []
            option_groups[name].append(value)

            # 개별 옵션 정보 저장
            parsed_options.append(
                {
                    "name": name,
                    "value": value,
                    "price": float(option.get("price", 0)),
                    "stock": int(option.get("stock", 0)),
                    "sku": option.get("sku", ""),
                }
            )

        # 옵션 그룹 정보도 함께 반환
        result = {
            "items": parsed_options,
            "groups": [
                {"name": name, "values": list(set(values))}
                for name, values in option_groups.items()
            ],
        }

        return result

    def parse_categories(self, categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """카테고리 목록 파싱

        Args:
            categories: 원본 카테고리 목록

        Returns:
            파싱된 카테고리 목록
        """
        parsed_categories = []

        for category in categories:
            parsed_cat = {
                "id": category.get("id", ""),
                "name": category.get("name", "").strip(),
                "parent_id": category.get("parent_id", ""),
                "level": int(category.get("level", 1)),
                "path": category.get("path", ""),
                "is_active": category.get("is_active", True),
            }

            # 전체 경로 생성 (부모 카테고리가 있는 경우)
            if not parsed_cat["path"] and parsed_cat["parent_id"]:
                # 부모 카테고리 찾기
                parent = next((c for c in categories if c["id"] == parsed_cat["parent_id"]), None)
                if parent:
                    parent_path = parent.get("path", parent.get("name", ""))
                    parsed_cat["path"] = f"{parent_path} > {parsed_cat['name']}"
            elif not parsed_cat["path"]:
                parsed_cat["path"] = parsed_cat["name"]

            parsed_categories.append(parsed_cat)

        return parsed_categories

    def parse_error(self, response: Any) -> Optional[str]:
        """에러 응답 파싱

        Args:
            response: 에러 응답

        Returns:
            에러 메시지 또는 None
        """
        if isinstance(response, str):
            return response
        elif isinstance(response, dict):
            return response.get("error", response.get("message", "Unknown error"))
        else:
            return str(response) if response else None
