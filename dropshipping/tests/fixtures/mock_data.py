"""
테스트용 Mock 데이터 생성기
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
from faker import Faker

from dropshipping.models.product import (
    StandardProduct,
    ProductImage,
    ProductOption,
    ProductVariant,
    ProductStatus,
    OptionType,
)


fake = Faker("ko_KR")


class MockDataGenerator:
    """테스트용 Mock 데이터 생성"""

    CATEGORIES = {
        "fashion": {
            "name": "패션",
            "subcategories": ["여성의류", "남성의류", "신발", "가방", "액세서리"],
            "brands": ["나이키", "아디다스", "자라", "유니클로", "H&M"],
            "options": [
                {"name": "색상", "values": ["블랙", "화이트", "네이비", "그레이", "베이지"]},
                {"name": "사이즈", "values": ["S", "M", "L", "XL", "XXL"]},
            ],
        },
        "beauty": {
            "name": "뷰티",
            "subcategories": ["스킨케어", "메이크업", "헤어케어", "바디케어", "향수"],
            "brands": ["아모레퍼시픽", "LG생활건강", "에스티로더", "로레알", "시세이도"],
            "options": [
                {"name": "용량", "values": ["30ml", "50ml", "100ml", "150ml", "200ml"]},
                {"name": "타입", "values": ["지성용", "건성용", "복합성용", "민감성용"]},
            ],
        },
        "electronics": {
            "name": "전자제품",
            "subcategories": ["스마트폰", "노트북", "태블릿", "이어폰", "스마트워치"],
            "brands": ["삼성", "애플", "LG", "소니", "보스"],
            "options": [
                {"name": "색상", "values": ["블랙", "실버", "골드", "블루", "레드"]},
                {"name": "용량", "values": ["64GB", "128GB", "256GB", "512GB", "1TB"]},
            ],
        },
    }

    SUPPLIERS = ["domeme", "ownerclan", "zentrade", "excel"]

    @classmethod
    def generate_product(
        cls,
        supplier_id: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[ProductStatus] = None,
    ) -> StandardProduct:
        """단일 상품 생성"""

        # 공급사 선택
        if not supplier_id:
            supplier_id = random.choice(cls.SUPPLIERS)

        # 카테고리 선택
        if not category:
            category = random.choice(list(cls.CATEGORIES.keys()))

        category_info = cls.CATEGORIES[category]

        # 상품 ID 생성
        product_id = f"{supplier_id}_{fake.uuid4()[:8]}"

        # 기본 정보
        subcategory = random.choice(category_info["subcategories"])
        brand = random.choice(category_info["brands"])

        # 가격 생성
        cost = Decimal(str(random.randint(5000, 100000)))
        margin_rate = Decimal(str(random.uniform(0.2, 0.5)))  # 20~50% 마진
        price = cost * (1 + margin_rate)
        list_price = price * Decimal("1.1")  # 10% 할인가로 판매

        # 재고 및 상태
        stock = random.randint(0, 1000)
        if not status:
            if stock == 0:
                status = ProductStatus.SOLDOUT
            elif random.random() < 0.9:
                status = ProductStatus.ACTIVE
            else:
                status = ProductStatus.INACTIVE

        # 이미지 생성
        images = cls._generate_images(3)

        # 옵션 생성
        options = cls._generate_options(category_info["options"])

        # 변형 생성
        variants = cls._generate_variants(options) if options else []

        # 배송 정보
        is_free_shipping = price > 30000 or random.random() < 0.3
        shipping_fee = Decimal("0") if is_free_shipping else Decimal("3000")

        # 태그 생성
        tags = [category_info["name"], subcategory, brand]
        tags.extend(fake.words(nb=random.randint(3, 7)))

        return StandardProduct(
            id=product_id,
            supplier_id=supplier_id,
            supplier_product_id=fake.uuid4()[:12],
            name=f"{brand} {subcategory} {fake.catch_phrase()}",
            description=fake.text(max_nb_chars=500),
            brand=brand,
            manufacturer=fake.company(),
            origin=random.choice(["국내산", "중국", "베트남", "미국", "일본"]),
            category_code=f"{category}_{subcategory}",
            category_name=subcategory,
            category_path=[category_info["name"], subcategory],
            cost=cost,
            price=price,
            list_price=list_price,
            stock=stock,
            status=status,
            images=images,
            options=options,
            variants=variants,
            shipping_fee=shipping_fee,
            is_free_shipping=is_free_shipping,
            shipping_method=random.choice(["택배", "퀵배송", "직배송"]),
            attributes={
                "weight": f"{random.randint(100, 5000)}g",
                "size": f"{random.randint(10, 100)}x{random.randint(10, 100)}x{random.randint(10, 100)}mm",
                "material": fake.word(),
            },
            tags=tags,
            created_at=fake.date_time_between(start_date="-30d", end_date="now"),
            updated_at=datetime.now(),
        )

    @classmethod
    def generate_products(
        cls, count: int = 10, supplier_id: Optional[str] = None, category: Optional[str] = None
    ) -> List[StandardProduct]:
        """여러 상품 생성"""
        return [cls.generate_product(supplier_id, category) for _ in range(count)]

    @classmethod
    def _generate_images(cls, count: int = 3) -> List[ProductImage]:
        """이미지 생성"""
        images = []
        for i in range(count):
            images.append(
                ProductImage(
                    url=f"https://picsum.photos/800/800?random={fake.uuid4()[:8]}",
                    alt=f"상품 이미지 {i+1}",
                    is_main=(i == 0),
                    order=i,
                    width=800,
                    height=800,
                )
            )
        return images

    @classmethod
    def _generate_options(cls, option_templates: List[Dict]) -> List[ProductOption]:
        """옵션 생성"""
        options = []
        for template in random.sample(option_templates, k=random.randint(1, 2)):
            options.append(
                ProductOption(
                    name=template["name"],
                    type=OptionType.SELECT,
                    values=random.sample(
                        template["values"], k=min(random.randint(2, 5), len(template["values"]))
                    ),
                    required=True,
                )
            )
        return options

    @classmethod
    def _generate_variants(cls, options: List[ProductOption]) -> List[ProductVariant]:
        """변형 생성 (옵션 조합)"""
        if not options:
            return []

        variants = []

        # 간단히 각 옵션의 첫 번째 값들만 조합
        for i in range(min(5, len(options[0].values))):
            option_values = {}
            for opt in options:
                if i < len(opt.values):
                    option_values[opt.name] = opt.values[i]
                else:
                    option_values[opt.name] = opt.values[0]

            variants.append(
                ProductVariant(
                    sku=f"SKU_{fake.uuid4()[:8]}",
                    options=option_values,
                    stock=random.randint(0, 100),
                    status=ProductStatus.ACTIVE,
                )
            )

        return variants

    @classmethod
    def generate_domeme_response(cls, count: int = 10) -> str:
        """도매매 API 응답 XML 생성"""
        products_xml = []

        for _ in range(count):
            product = cls.generate_product(supplier_id="domeme")
            product_xml = f"""
            <product>
                <productNo>{product.supplier_product_id}</productNo>
                <productNm>{product.name}</productNm>
                <brandNm>{product.brand}</brandNm>
                <makerNm>{product.manufacturer}</makerNm>
                <origin>{product.origin}</origin>
                <supplyPrice>{int(product.cost)}</supplyPrice>
                <salePrice>{int(product.price)}</salePrice>
                <consumerPrice>{int(product.list_price)}</consumerPrice>
                <stockQty>{product.stock}</stockQty>
                <productStatus>{'Y' if product.status == ProductStatus.ACTIVE else 'N'}</productStatus>
                <category1>{product.category_code}</category1>
                <categoryNm1>{product.category_name}</categoryNm1>
                <mainImg>{product.main_image.url if product.main_image else ''}</mainImg>
                <deliveryPrice>{int(product.shipping_fee)}</deliveryPrice>
                <deliveryType>{product.shipping_method}</deliveryType>
                <description>{product.description}</description>
            </product>
            """
            products_xml.append(product_xml.strip())

        return f"""<?xml version="1.0" encoding="UTF-8"?>
        <result>
            <code>00</code>
            <message>성공</message>
            <totalCount>{count}</totalCount>
            <productList>
                {''.join(products_xml)}
            </productList>
        </result>"""

    @classmethod
    def generate_raw_product_data(cls, supplier_id: str = "domeme") -> Dict[str, Any]:
        """공급사별 원본 데이터 형식 생성"""
        product = cls.generate_product(supplier_id=supplier_id)

        if supplier_id == "domeme":
            return {
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
                "mainImg": product.main_image.url if product.main_image else "",
                "deliveryPrice": str(product.shipping_fee),
                "deliveryType": product.shipping_method,
                "description": product.description,
            }

        # 다른 공급사 형식 추가 가능
        return product.to_dict()
