"""
테스트용 Mock Fetcher
실제 API 없이 개발/테스트할 수 있도록 가짜 데이터 제공
"""

from datetime import datetime
from typing import Any, Dict, List, Tuple

from dropshipping.models.product import ProductStatus
from dropshipping.suppliers.base.base_fetcher import BaseFetcher
from dropshipping.tests.fixtures.mock_data import MockDataGenerator


class MockFetcher(BaseFetcher):
    """테스트용 Mock 데이터 Fetcher"""

    def __init__(self, storage=None, transformer=None):
        super().__init__(storage, supplier_name="mock")
        self.products_per_page = 10
        self.total_products = 50  # 총 상품 수
        self._generated_products = []  # 생성된 상품 캐시
        self._generate_all_products()
        # 통계 추가
        self._stats = {"fetched": 0, "saved": 0, "duplicates": 0, "errors": 0}

    def _generate_all_products(self):
        """모든 상품 미리 생성 (일관성 보장)"""
        self._generated_products = []
        for i in range(self.total_products):
            product = MockDataGenerator.generate_product(supplier_id="mock")
            # 인덱스 기반 ID로 변경
            product.id = f"mock_{i+1:04d}"
            product.supplier_product_id = f"MOCK{i+1:04d}"

            # raw 데이터 형식으로 변환
            raw_data = {
                "productNo": product.supplier_product_id,
                "productNm": product.name,
                "brandNm": product.brand,
                "makerNm": product.manufacturer,
                "origin": product.origin,
                "supplyPrice": str(product.cost),
                "salePrice": str(product.price),
                "consumerPrice": str(product.list_price),
                "stockQty": str(product.stock),
                "productStatus": "Y" if product.status == ProductStatus.ACTIVE else "N",
                "category1": product.category_code,
                "categoryNm1": product.category_name,
                "mainImg": str(product.main_image.url) if product.main_image else "",
                "deliveryPrice": str(product.shipping_fee),
                "deliveryType": product.shipping_method,
                "description": product.description,
                "regDate": product.created_at.isoformat(),
                "updateDate": product.updated_at.isoformat(),
            }

            self._generated_products.append(raw_data)

    def fetch_list(self, page: int = 1, **kwargs) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Mock 상품 목록 조회

        Args:
            page: 페이지 번호
            **kwargs: 추가 파라미터 (since 등)

        Returns:
            Tuple[상품 목록, 다음 페이지 존재 여부]
        """
        since = kwargs.get("since")

        # 페이지네이션 계산
        start_idx = (page - 1) * self.products_per_page
        end_idx = start_idx + self.products_per_page

        # 전체 상품에서 페이지에 해당하는 부분 추출
        page_products = self._generated_products[start_idx:end_idx]

        # since 필터링
        if since and isinstance(since, datetime):
            page_products = [
                p for p in page_products if datetime.fromisoformat(p.get("regDate", "")) >= since
            ]

        # 다음 페이지 존재 여부
        has_next = end_idx < self.total_products

        return page_products, has_next

    def fetch_detail(self, product_id: str) -> Dict[str, Any]:
        """
        Mock 상품 상세 정보 조회

        Args:
            product_id: 상품 ID

        Returns:
            상품 상세 정보
        """
        # ID로 상품 찾기
        for product in self._generated_products:
            if product["productNo"] == product_id:
                # 상세 정보 추가
                detail = product.copy()
                detail.update(
                    {
                        "detailHtml": f"<h1>{product['productNm']}</h1><p>상세 설명입니다.</p>",
                        "keywords": ["테스트", "상품", "키워드"],
                        "addImg1": "https://picsum.photos/800/800?random=1",
                        "addImg2": "https://picsum.photos/800/800?random=2",
                        "addImg3": "https://picsum.photos/800/800?random=3",
                        "option1Nm": "색상",
                        "option1Value": "빨강,파랑,노랑",
                        "option2Nm": "사이즈",
                        "option2Value": "S,M,L,XL",
                    }
                )
                return detail

        raise ValueError(f"상품을 찾을 수 없습니다: {product_id}")

    def needs_detail_fetch(self, list_item: Dict[str, Any]) -> bool:
        """
        Mock에서는 목록 API에 상세 정보가 없다고 가정
        """
        return True

    def set_total_products(self, count: int):
        """테스트용: 총 상품 수 설정"""
        self.total_products = count
        self._generate_all_products()

    def set_products_per_page(self, count: int):
        """테스트용: 페이지당 상품 수 설정"""
        self.products_per_page = count

    @property
    def stats(self):
        """통계 반환"""
        return self._stats.copy()
