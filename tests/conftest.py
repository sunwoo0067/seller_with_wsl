"""
pytest 공통 fixtures 및 설정
"""

import os
import sys
from pathlib import Path
from typing import Generator
import pytest
from unittest.mock import Mock, patch

# 프로젝트 루트를 Python 경로에 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def test_env():
    """테스트 환경 설정"""
    # 테스트용 환경 변수 설정
    os.environ["ENV"] = "test"
    os.environ["DEBUG"] = "true"
    os.environ["DRY_RUN"] = "true"
    os.environ["LOG_LEVEL"] = "DEBUG"
    os.environ["CACHE_ENABLED"] = "false"

    # 테스트용 데이터 경로
    os.environ["LOCAL_DATA_PATH"] = "./tests/data"
    os.environ["LOCAL_UPLOAD_PATH"] = "./tests/uploads"

    yield

    # 테스트 후 정리 (필요시)


@pytest.fixture
def mock_settings(test_env):
    """Mock 설정 객체"""
    from dropshipping.config import Settings

    settings = Settings(
        env="test",
        debug=True,
        dry_run=True,
        log_level="DEBUG",
        cache_enabled=False,
        local_data_path=Path("./tests/data"),
        local_upload_path=Path("./tests/uploads"),
    )

    with patch("dropshipping.config.get_settings", return_value=settings):
        yield settings


@pytest.fixture
def mock_requests(monkeypatch):
    """requests 라이브러리 Mock"""
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json.return_value = {
        "resultCode": "00",
        "message": "성공",
        "product": [],
        "totalCount": 0,
    }

    mock_get = Mock(return_value=mock_response)
    monkeypatch.setattr("requests.get", mock_get)
    
    return mock_get


@pytest.fixture
def sample_product_data():
    """샘플 상품 데이터"""
    return {
        "id": "TEST001",
        "name": "테스트 상품",
        "price": 10000,
        "cost": 7000,
        "category": "의류",
        "supplier": "domeme",
        "description": "테스트 상품 설명입니다.",
        "images": ["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
        "options": [
            {"name": "색상", "values": ["빨강", "파랑"]},
            {"name": "사이즈", "values": ["S", "M", "L"]},
        ],
        "stock": 100,
        "status": "active",
    }


@pytest.fixture
def sample_domeme_response():
    """도매매 API 응답 샘플"""
    return """<?xml version="1.0" encoding="UTF-8"?>
    <result>
        <code>00</code>
        <message>성공</message>
        <productList>
            <product>
                <productNo>TEST001</productNo>
                <productNm>테스트 상품</productNm>
                <supplyPrice>7000</supplyPrice>
                <category1>의류</category1>
                <description>테스트 상품 설명입니다.</description>
                <mainImg>https://example.com/image1.jpg</mainImg>
                <stockQty>100</stockQty>
            </product>
        </productList>
    </result>"""


@pytest.fixture
def temp_data_dir(tmp_path):
    """임시 데이터 디렉터리"""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase 클라이언트"""
    client = Mock()

    # 테이블 mock
    table = Mock()
    table.insert = Mock(return_value=Mock(execute=Mock(return_value=Mock(data=[]))))
    table.select = Mock(return_value=Mock(execute=Mock(return_value=Mock(data=[]))))
    table.update = Mock(return_value=Mock(execute=Mock(return_value=Mock(data=[]))))
    table.delete = Mock(return_value=Mock(execute=Mock(return_value=Mock(data=[]))))

    client.table = Mock(return_value=table)

    return client


@pytest.fixture(autouse=True)
def cleanup_test_files():
    """테스트 파일 자동 정리"""
    yield

    # 테스트 중 생성된 파일 정리
    test_paths = ["./tests/data", "./tests/uploads", "./tests/logs"]
    for path in test_paths:
        if Path(path).exists():
            import shutil

            shutil.rmtree(path, ignore_errors=True)
