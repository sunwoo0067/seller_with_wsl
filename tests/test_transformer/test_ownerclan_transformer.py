import pytest
from decimal import Decimal
from dropshipping.suppliers.ownerclan.transformer import OwnerclanTransformer
from dropshipping.models.product import StandardProduct, ProductStatus


@pytest.fixture
def transformer():
    """Returns an OwnerclanTransformer instance."""
    return OwnerclanTransformer()


@pytest.fixture
def raw_single_product():
    """A raw product dictionary for a single item without options."""
    return {
        "id": "12345",
        "name": "기본 티셔츠",
        "price": 10000.0,
        "fixed_price": 12000.0,
        "stock": 50,
        "brand": "기본 브랜드",
        "origin": "대한민국",
        "category": "의류/상의",
        "images": ["/img/tshirt.jpg"],
        "options": [],
        "shipping_fee": 3000.0,
        "shipping_type": "paid",
        "status": "AVAILABLE",
        "tax_free": False,
        "adult_only": False,
        "returnable": True,
    }


@pytest.fixture
def raw_variant_product():
    """A raw product dictionary for an item with options."""
    return {
        "id": "67890",
        "name": "옵션 티셔츠",
        "price": 15000.0,
        "fixed_price": 0,
        "stock": 100,  # This stock is calculated by parser from options
        "brand": "옵션 브랜드",
        "origin": "중국",
        "category": "의류/상의/반팔티",
        "images": ["/img/option_tshirt_main.jpg", "/img/option_tshirt_sub.jpg"],
        "options": [
            {
                "name": "색상: 블랙, 사이즈: M",
                "price": 15000.0,
                "quantity": 30,
                "attributes": {"색상": "블랙", "사이즈": "M"},
            },
            {
                "name": "색상: 화이트, 사이즈: M",
                "price": 15000.0,
                "quantity": 30,
                "attributes": {"색상": "화이트", "사이즈": "M"},
            },
            {
                "name": "색상: 블랙, 사이즈: L",
                "price": 16000.0,
                "quantity": 40,
                "attributes": {"색상": "블랙", "사이즈": "L"},
            },
        ],
        "shipping_fee": 0,
        "shipping_type": "free",
        "status": "AVAILABLE",
        "tax_free": True,
        "adult_only": False,
        "returnable": True,
    }


def test_transform_single_product(transformer, raw_single_product):
    """Tests transformation of a single product without variants."""
    product = transformer.to_standard(raw_single_product)

    assert isinstance(product, StandardProduct)
    assert product.id == "ownerclan_12345"
    assert product.supplier_product_id == "12345"
    assert product.name == "기본 티셔츠"
    assert product.brand == "기본 브랜드"
    assert product.cost == Decimal("10000.0")
    assert product.list_price == Decimal("12000.0")
    assert product.price == Decimal("13000.0")  # 10000 * 1.3, rounded
    assert product.stock == 50
    assert product.status == ProductStatus.ACTIVE
    assert len(product.images) == 1
    assert str(product.images[0].url) == "https://ownerclan.com/img/tshirt.jpg"
    assert product.images[0].is_main is True
    assert not product.options
    assert not product.variants
    assert product.shipping_fee == Decimal("3000.0")
    assert product.is_free_shipping is False


def test_transform_variant_product(transformer, raw_variant_product):
    """Tests transformation of a product with variants."""
    product = transformer.to_standard(raw_variant_product)

    assert isinstance(product, StandardProduct)
    assert product.id == "ownerclan_67890"
    assert product.name == "옵션 티셔츠"
    assert product.cost == Decimal("15000.0")
    assert product.list_price is None  # fixed_price is 0
    assert product.price == Decimal("19500.0")  # 15000 * 1.3
    assert product.stock == 100  # Sum of variant stocks
    assert len(product.images) == 2
    assert product.images[0].is_main is True
    assert product.images[1].is_main is False

    # Check options
    assert len(product.options) == 2
    option_names = {opt.name for opt in product.options}
    assert option_names == {"색상", "사이즈"}
    for opt in product.options:
        if opt.name == "색상":
            assert sorted(opt.values) == ["블랙", "화이트"]
        if opt.name == "사이즈":
            assert sorted(opt.values) == ["L", "M"]

    # Check variants
    assert len(product.variants) == 3
    variant1 = product.variants[0]
    assert variant1.sku == "OC-67890-1"
    assert variant1.options == {"색상": "블랙", "사이즈": "M"}
    assert variant1.price == Decimal("15000.0")
    assert variant1.stock == 30

    variant3 = product.variants[2]
    assert variant3.sku == "OC-67890-3"
    assert variant3.options == {"색상": "블랙", "사이즈": "L"}
    assert variant3.price == Decimal("16000.0")
    assert variant3.stock == 40

    assert product.is_free_shipping is True


def test_transform_invalid_product(transformer):
    """Tests transformation with missing required fields."""
    # Missing 'id'
    invalid_data_1 = {"name": "Invalid Product"}
    product1 = transformer.to_standard(invalid_data_1)
    assert product1 is None

    # Missing 'name'
    invalid_data_2 = {"id": "no-name"}
    product2 = transformer.to_standard(invalid_data_2)
    assert product2 is None

    # Empty data
    product3 = transformer.to_standard({})
    assert product3 is None


def test_calculate_selling_price(transformer):
    """Tests the selling price calculation logic."""
    assert transformer._calculate_selling_price(10000) == 13000
    assert transformer._calculate_selling_price(12345) == 16000  # 12345 * 1.3 = 16048.5 -> 16000
    assert transformer._calculate_selling_price(99) == 100  # 99 * 1.3 = 128.7 -> 100
