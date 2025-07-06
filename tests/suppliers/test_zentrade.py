"""
젠트레이드 공급사 통합 테스트
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import xml.etree.ElementTree as ET
from io import BytesIO

from dropshipping.suppliers.zentrade.fetcher import ZentradeFetcher
from dropshipping.suppliers.zentrade.parser import ZentradeParser
from dropshipping.suppliers.zentrade.transformer import ZentradeTransformer
from dropshipping.models.product import StandardProduct


@pytest.fixture
def mock_storage():
    """Mock storage"""
    storage = Mock()
    storage.save_raw_products = Mock(return_value=None)
    storage.save_processed_products = Mock(return_value=None)
    return storage


@pytest.fixture
def zentrade_fetcher(mock_storage):
    """Zentrade fetcher fixture"""
    return ZentradeFetcher(
        storage=mock_storage,
        supplier_name="zentrade",
        ftp_host="ftp.zentrade.co.kr",
        ftp_user="test_user",
        ftp_pass="test_pass"
    )


@pytest.fixture
def sample_xml_data():
    """샘플 XML 데이터"""
    xml_str = """<?xml version="1.0" encoding="UTF-8"?>
    <products>
        <product>
            <product_id>ZT001</product_id>
            <product_name>테스트 상품 1</product_name>
            <category>가전/디지털</category>
            <brand>테스트브랜드</brand>
            <model>TEST-001</model>
            <price>10000</price>
            <stock>50</stock>
            <description>테스트 상품 설명입니다.</description>
            <status>active</status>
            <images>
                <image>https://example.com/image1.jpg</image>
                <image>https://example.com/image2.jpg</image>
            </images>
            <options>
                <option name="색상" value="블랙" price="10000" stock="25"/>
                <option name="색상" value="화이트" price="10000" stock="25"/>
            </options>
            <shipping>
                <method>기본배송</method>
                <fee>3000</fee>
                <free_condition>50000</free_condition>
            </shipping>
        </product>
        <product>
            <product_id>ZT002</product_id>
            <product_name>테스트 상품 2</product_name>
            <category>패션/의류</category>
            <brand>패션브랜드</brand>
            <price>20000</price>
            <stock>100</stock>
            <status>active</status>
        </product>
    </products>"""
    return xml_str.encode('utf-8')


@pytest.fixture
def parsed_product():
    """파싱된 상품 데이터"""
    return {
        "id": "ZT001",
        "name": "테스트 상품 1",
        "category": "가전/디지털",
        "brand": "테스트브랜드",
        "model": "TEST-001",
        "price": 10000,
        "stock": 50,
        "description": "테스트 상품 설명입니다.",
        "status": "active",
        "images": ["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
        "options": {
            "items": [
                {"name": "색상", "value": "블랙", "price": 10000, "stock": 25},
                {"name": "색상", "value": "화이트", "price": 10000, "stock": 25}
            ],
            "groups": [
                {"name": "색상", "values": ["블랙", "화이트"]}
            ]
        },
        "shipping_fee": 3000,
        "shipping_method": "기본배송",
        "shipping_free_condition": 50000
    }


class TestZentradeFetcher:
    """Zentrade Fetcher 테스트"""
    
    @patch('ftplib.FTP')
    def test_connect_ftp(self, mock_ftp_class, zentrade_fetcher):
        """FTP 연결 테스트"""
        mock_ftp = Mock()
        mock_ftp_class.return_value = mock_ftp
        
        ftp = zentrade_fetcher._connect_ftp()
        
        assert ftp == mock_ftp
        mock_ftp.connect.assert_called_once_with("ftp.zentrade.co.kr", timeout=30)
        mock_ftp.login.assert_called_once_with("test_user", "test_pass")
    
    def test_parse_xml(self, zentrade_fetcher, sample_xml_data):
        """XML 파싱 테스트"""
        products = zentrade_fetcher._parse_xml(sample_xml_data)
        
        assert len(products) == 2
        assert products[0]["id"] == "ZT001"
        assert products[0]["name"] == "테스트 상품 1"
        assert len(products[0]["images"]) == 2
        assert len(products[0]["options"]) == 2
    
    @patch('ftplib.FTP')
    def test_fetch_list(self, mock_ftp_class, zentrade_fetcher, sample_xml_data):
        """상품 목록 조회 테스트"""
        # FTP 모킹
        mock_ftp = Mock()
        mock_ftp_class.return_value = mock_ftp
        
        # 파일 목록 모킹
        files = [
            "drwxr-xr-x    2 user  group  4096 Jan 1 00:00 .",
            "-rw-r--r--    1 user  group  1234 Jan 1 00:00 products.xml"
        ]
        mock_ftp.retrlines.side_effect = lambda cmd, callback: [callback(f) for f in files]
        
        # 파일 다운로드 모킹
        mock_ftp.retrbinary.side_effect = lambda cmd, callback: callback(sample_xml_data)
        
        products = zentrade_fetcher.fetch_list()
        
        assert len(products) == 2
        assert products[0]["id"] == "ZT001"
        mock_ftp.quit.assert_called_once()


class TestZentradeParser:
    """Zentrade Parser 테스트"""
    
    def test_parse_products(self):
        """상품 목록 파싱 테스트"""
        parser = ZentradeParser()
        raw_products = [
            {"id": "ZT001", "name": "상품1", "price": 10000},
            {"id": "ZT002", "name": "상품2", "price": 20000}
        ]
        
        products = parser.parse_products(raw_products)
        
        assert len(products) == 2
        assert products[0]["id"] == "ZT001"
        assert products[0]["price"] == 10000
    
    def test_normalize_product(self, parsed_product):
        """상품 정규화 테스트"""
        parser = ZentradeParser()
        product = parser._normalize_product(parsed_product)
        
        assert product["id"] == "ZT001"
        assert product["status"] == "active"
        assert product["shipping_fee"] == 3000
        assert product["stock"] == 50
        
        # 옵션 처리 확인
        options = product["options"]
        assert len(options["items"]) == 2
        assert len(options["groups"]) == 1
        assert options["groups"][0]["name"] == "색상"


class TestZentradeTransformer:
    """Zentrade Transformer 테스트"""
    
    def test_transform_basic(self, parsed_product):
        """기본 변환 테스트"""
        transformer = ZentradeTransformer()
        product = transformer.to_standard(parsed_product)
        
        assert isinstance(product, StandardProduct)
        assert product.supplier_id == "zentrade"
        assert product.supplier_product_id == "ZT001"
        assert product.name == "테스트 상품 1"
        assert product.brand == "테스트브랜드"
        assert float(product.cost) == 10000
        assert float(product.price) == 13000  # 30% 마진
        assert product.stock == 50
    
    def test_transform_options(self, parsed_product):
        """옵션 변환 테스트"""
        transformer = ZentradeTransformer()
        product = transformer.to_standard(parsed_product)
        
        assert len(product.options) == 1
        assert product.options[0].name == "색상"
        assert set(product.options[0].values) == {"블랙", "화이트"}
        
        assert len(product.variants) == 2
        assert product.variants[0].stock == 25
    
    def test_transform_shipping(self, parsed_product):
        """배송 정보 변환 테스트"""
        transformer = ZentradeTransformer()
        product = transformer.to_standard(parsed_product)
        
        assert product.shipping_method == "조건부 무료배송"
        assert float(product.shipping_fee) == 3000
        assert not product.is_free_shipping


@pytest.mark.integration
class TestZentradeIntegration:
    """젠트레이드 통합 테스트"""
    
    @patch('ftplib.FTP')
    def test_full_pipeline(self, mock_ftp_class, mock_storage, sample_xml_data):
        """전체 파이프라인 테스트"""
        # FTP 모킹
        mock_ftp = Mock()
        mock_ftp_class.return_value = mock_ftp
        
        files = ["-rw-r--r-- 1 user group 1234 Jan 1 00:00 products.xml"]
        mock_ftp.retrlines.side_effect = lambda cmd, callback: [callback(f) for f in files]
        mock_ftp.retrbinary.side_effect = lambda cmd, callback: callback(sample_xml_data)
        
        # 컴포넌트 초기화
        fetcher = ZentradeFetcher(
            storage=mock_storage,
            supplier_name="zentrade",
            ftp_host="ftp.zentrade.co.kr",
            ftp_user="test",
            ftp_pass="test"
        )
        parser = ZentradeParser()
        transformer = ZentradeTransformer()
        
        # 실행
        raw_products = fetcher.fetch_list()
        parsed_products = parser.parse_products(raw_products)
        
        # 첫 번째 상품 변환
        parsed = parser._normalize_product(parsed_products[0])
        standard_product = transformer.to_standard(parsed)
        
        # 검증
        assert standard_product is not None
        assert standard_product.supplier_product_id == "ZT001"
        assert standard_product.name == "테스트 상품 1"
        assert len(standard_product.options) == 1
        assert standard_product.stock == 50