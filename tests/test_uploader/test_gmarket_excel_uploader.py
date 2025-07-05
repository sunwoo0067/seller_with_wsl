"""
G마켓/옥션 Excel 업로더 테스트
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd
import pytest

from dropshipping.models.product import ProductImage, ProductVariant, StandardProduct
from dropshipping.storage.base import BaseStorage
from dropshipping.uploader.base import MarketplaceType, UploadStatus
from dropshipping.uploader.gmarket_excel.gmarket_excel_uploader import GmarketExcelUploader


class TestGmarketExcelUploader:
    """GmarketExcelUploader 테스트"""

    @pytest.fixture
    def mock_storage(self):
        """Mock 저장소"""
        return Mock(spec=BaseStorage)

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """임시 디렉터리"""
        return tmp_path / "excel_test"

    @pytest.fixture
    def uploader(self, mock_storage, temp_dir):
        """테스트용 G마켓 Excel 업로더"""
        config = {
            "output_dir": str(temp_dir),
            "marketplace": "gmarket",
            "seller_code": "TEST_SELLER",
            "shipping_address": "서울특별시 강남구 테스트동",
            "return_address": "서울특별시 강남구 반품동",
        }
        return GmarketExcelUploader(storage=mock_storage, config=config)

    @pytest.fixture
    def sample_products(self):
        """테스트용 상품 목록"""
        return [
            StandardProduct(
                id="gm-test-001",
                supplier_id="domeme",
                supplier_product_id="DM001",
                name="테스트 블루투스 이어폰",
                description="고품질 이어폰",
                price=29900,
                cost=15000,
                category_name="전자기기/이어폰",
                stock=100,
                brand="TestBrand",
                images=[
                    ProductImage(url="https://example.com/main.jpg", is_main=True),
                    ProductImage(url="https://example.com/sub1.jpg", is_main=False),
                ],
                attributes={"manufacturer": "테스트 제조사"},
            ),
            StandardProduct(
                id="gm-test-002",
                supplier_id="domeme",
                supplier_product_id="DM002",
                name="여성 니트 스웨터",
                price=19900,
                cost=10000,
                category_name="의류/여성의류",
                stock=50,
                variants=[
                    ProductVariant(
                        sku="gm-test-002-S", options={"사이즈": "S"}, price=19900, stock=20
                    ),
                    ProductVariant(
                        sku="gm-test-002-M", options={"사이즈": "M"}, price=19900, stock=30
                    ),
                ],
            ),
        ]

    def test_init(self, uploader, temp_dir):
        """초기화 테스트"""
        assert uploader.marketplace == MarketplaceType.GMARKET
        assert uploader.seller_code == "TEST_SELLER"
        assert uploader.output_dir == temp_dir
        assert temp_dir.exists()

    def test_validate_product_success(self, uploader, sample_products):
        """상품 검증 성공 테스트"""
        is_valid, error = asyncio.run(uploader.validate_product(sample_products[0]))

        assert is_valid is True
        assert error is None

    def test_validate_product_fail(self, uploader):
        """상품 검증 실패 테스트"""
        invalid_product = StandardProduct(
            id="invalid-001",
            supplier_id="test",
            supplier_product_id="TEST001",
            name="",  # 빈 상품명
            price=200,  # 너무 낮은 가격
            cost=100,
            category_name="미지원카테고리",
            stock=0,
        )

        is_valid, error = asyncio.run(uploader.validate_product(invalid_product))

        assert is_valid is False
        assert "상품명 누락" in error
        assert "판매가격이 너무 낮습니다" in error
        assert "지원하지 않는 카테고리" in error

    def test_transform_product_basic(self, uploader, sample_products):
        """기본 상품 변환 테스트"""
        excel_data = asyncio.run(uploader.transform_product(sample_products[0]))

        assert excel_data["상품명"] == "테스트 블루투스 이어폰"
        assert excel_data["판매가"] == 29900
        assert excel_data["재고수량"] == 100
        assert excel_data["카테고리코드"] == "200001541"
        assert excel_data["브랜드"] == "TestBrand"
        assert excel_data["제조사"] == "테스트 제조사"
        assert excel_data["배송비유형"] == "조건부무료"
        assert excel_data["배송비"] == 2500
        assert excel_data["상품이미지1"] == "https://example.com/main.jpg"
        assert excel_data["상품이미지2"] == "https://example.com/sub1.jpg"
        assert excel_data["옵션사용여부"] == "N"
        assert excel_data["판매자상품코드"] == "gm-test-001"

    def test_transform_product_with_options(self, uploader, sample_products):
        """옵션이 있는 상품 변환 테스트"""
        excel_data = asyncio.run(uploader.transform_product(sample_products[1]))

        assert excel_data["옵션사용여부"] == "Y"
        assert excel_data["옵션명"] == "사이즈"
        assert excel_data["옵션값"] == "S,M"
        assert excel_data["옵션가격"] == "0,0"
        assert excel_data["옵션재고"] == "20,30"

    def test_create_detail_html(self, uploader, sample_products):
        """상세 설명 HTML 생성 테스트"""
        html = uploader._create_detail_html(sample_products[0])

        assert "테스트 블루투스 이어폰" in html
        assert "G마켓 공식 판매점" in html
        assert "TestBrand" in html
        assert "테스트 제조사" in html
        assert "배송비: 2,500원" in html

    def test_upload_single_not_supported(self, uploader):
        """단일 업로드 미지원 테스트"""
        result = asyncio.run(uploader.upload_single({}))

        assert result["success"] is False
        assert "배치 업로드만 지원" in result["error"]

    def test_upload_batch_success(self, uploader, sample_products, temp_dir):
        """배치 업로드 성공 테스트"""
        # Excel 파일 생성을 mock
        with patch.object(uploader, "_create_excel_file", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "test_file.xlsx"

            results = asyncio.run(uploader.upload_batch(sample_products))

        assert len(results) == 2
        assert all(r["status"] == UploadStatus.SUCCESS for r in results)
        assert uploader.stats["uploaded"] == 2

        # 결과에 파일명이 포함되었는지 확인
        assert all("excel_file" in r for r in results if r["status"] == UploadStatus.SUCCESS)

    def test_upload_batch_with_invalid_products(self, uploader, sample_products):
        """유효하지 않은 상품이 포함된 배치 업로드 테스트"""
        # 유효하지 않은 상품 추가
        invalid_product = StandardProduct(
            id="invalid-001",
            supplier_id="test",
            supplier_product_id="TEST001",
            name="",
            price=100,
            cost=50,
            category_name="전자기기/이어폰",
            stock=0,
        )

        products = sample_products + [invalid_product]

        # Excel 파일 생성을 mock
        with patch.object(uploader, "_create_excel_file", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "test_file.xlsx"

            results = asyncio.run(uploader.upload_batch(products))

        assert len(results) == 3
        assert results[0]["status"] == UploadStatus.SUCCESS
        assert results[1]["status"] == UploadStatus.SUCCESS
        assert results[2]["status"] == UploadStatus.FAILED
        assert "상품명 누락" in results[2]["errors"][0]

    @pytest.mark.skip(reason="pandas와 openpyxl이 필요함")
    def test_create_excel_file(self, uploader, temp_dir):
        """Excel 파일 생성 테스트"""
        rows = [
            {
                "상품명": "테스트 상품 1",
                "판매가": 10000,
                "재고수량": 50,
                "카테고리코드": "200001541",
                "브랜드": "TestBrand",
            },
            {
                "상품명": "테스트 상품 2",
                "판매가": 20000,
                "재고수량": 30,
                "카테고리코드": "200000564",
                "브랜드": "TestBrand2",
            },
        ]

        filename = asyncio.run(uploader._create_excel_file(rows))

        assert filename.startswith("gmarket_upload_")
        assert filename.endswith(".xlsx")

        # 파일이 실제로 생성되었는지 확인
        filepath = temp_dir / filename
        assert filepath.exists()

        # Excel 파일 내용 확인
        df = pd.read_excel(filepath)
        assert len(df) == 2
        assert list(df.columns) == list(rows[0].keys())
        assert df.iloc[0]["상품명"] == "테스트 상품 1"
        assert df.iloc[1]["판매가"] == 20000

    def test_auction_uploader(self, mock_storage, temp_dir):
        """옥션 업로더 테스트"""
        config = {
            "output_dir": str(temp_dir),
            "marketplace": "auction",
            "seller_code": "TEST_SELLER",
        }

        uploader = GmarketExcelUploader(storage=mock_storage, config=config)

        assert uploader.marketplace == MarketplaceType.AUCTION

        # 상세 HTML에 옥션이 표시되는지 확인
        product = StandardProduct(
            id="test",
            supplier_id="test",
            supplier_product_id="TEST",
            name="테스트",
            price=10000,
            cost=5000,
            category_name="전자기기/이어폰",
            stock=10,
        )

        html = uploader._create_detail_html(product)
        assert "옥션 공식 판매점" in html
