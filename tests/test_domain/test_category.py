"""
카테고리 매핑 테스트
"""

import pytest
from unittest.mock import MagicMock, patch
import json
import tempfile
from pathlib import Path

from dropshipping.domain.category import CategoryMapper, CategoryMapping


from dropshipping.storage.base import BaseStorage


class TestCategoryMapperWithDB:
    """DB 연동 카테고리 매퍼 테스트"""

    @pytest.fixture
    def mock_storage(self):
        """DB Storage의 Mock 객체"""
        storage = MagicMock(spec=BaseStorage)
        
        # get_all_category_mappings의 Mock 반환값 설정
        storage.get_all_category_mappings.return_value = [
            {
                "supplier_id": "uuid-domeme",
                "marketplace_id": "uuid-coupang",
                "supplier_category_code": "DB001",
                "supplier_category_name": "DB패션",
                "marketplace_category_code": "DB194176",
                "marketplace_category_name": "DB여성패션",
                "confidence": 1.0
            }
        ]
        
        # ID-code 변환 Mock 설정
        storage.get_supplier_code.return_value = "domeme"
        storage.get_marketplace_code.return_value = "coupang"
        
        return storage

    def test_mapper_loads_from_db(self, mock_storage):
        """DB에서 매핑 정보를 성공적으로 로드하는지 테스트"""
        # CategoryMapper 초기화 시 storage 전달
        with patch.object(CategoryMapper, '_get_supplier_code', return_value='domeme'), \
             patch.object(CategoryMapper, '_get_marketplace_code', return_value='coupang'):
            mapper = CategoryMapper(storage=mock_storage)

            # DB에서 로드되었는지 확인
            assert len(mapper.mappings) > 0
            assert "domeme" in mapper.mappings
            assert "DB001" in mapper.mappings["domeme"]
            
            # get_marketplace_category가 DB 기반으로 동작하는지 확인
            result = mapper.get_marketplace_category(
                supplier_id="domeme",
                supplier_category_code="DB001",
                supplier_category_name="DB패션",
                marketplace="coupang"
            )
            
            assert result is not None
            assert result[0] == "DB194176"
            assert result[1] == "DB여성패션"


class TestCategoryMapper:
    """카테고리 매퍼 테스트"""

    @pytest.fixture
    def mapper(self):
        """테스트용 매퍼"""
        return CategoryMapper()

    def test_default_mappings(self, mapper):
        """기본 매핑 확인"""
        # 도매매 여성의류 -> 쿠팡 여성패션
        result = mapper.get_marketplace_category(
            supplier_id="domeme",
            supplier_category_code="001001",
            supplier_category_name="패션의류/여성의류",
            marketplace="coupang",
        )

        assert result is not None
        code, name, confidence = result
        assert code == "194176"
        assert name == "여성패션"
        assert confidence == 1.0

    def test_exact_mapping(self, mapper):
        """정확한 매핑"""
        # 커스텀 매핑 추가
        mapper.add_mapping(
            CategoryMapping(
                supplier_code="TEST001",
                supplier_name="테스트카테고리",
                marketplace="coupang",
                marketplace_code="999999",
                marketplace_name="테스트마켓카테고리",
            )
        )

        result = mapper.get_marketplace_category(
            supplier_id="domeme",
            supplier_category_code="TEST001",
            supplier_category_name="테스트카테고리",
            marketplace="coupang",
        )

        assert result is not None
        code, name, confidence = result
        assert code == "999999"
        assert name == "테스트마켓카테고리"

    def test_keyword_based_mapping(self, mapper):
        """키워드 기반 매핑"""
        # 여성 관련 키워드가 포함된 카테고리
        result = mapper.get_marketplace_category(
            supplier_id="unknown",
            supplier_category_code="UNKNOWN",
            supplier_category_name="여성 원피스 전문",
            marketplace="coupang",
        )

        assert result is not None
        code, name, confidence = result
        assert code == "194176"  # 여성패션
        assert 0 < confidence < 1.0  # 키워드 매칭은 신뢰도가 낮음

    def test_similarity_based_mapping(self, mapper):
        """유사도 기반 매핑"""
        # 기존 매핑과 유사한 이름
        result = mapper.get_marketplace_category(
            supplier_id="domeme",
            supplier_category_code="SIMILAR",
            supplier_category_name="패션의류/여자의류",  # 여성->여자
            marketplace="coupang",
        )

        assert result is not None
        code, name, confidence = result
        assert code == "194176"  # 여성패션으로 매칭되어야 함
        assert 0 < confidence < 1.0

    def test_multiple_marketplace_mapping(self, mapper):
        """동일 카테고리의 여러 마켓플레이스 매핑"""
        # 쿠팡 매핑
        coupang_result = mapper.get_marketplace_category(
            supplier_id="domeme",
            supplier_category_code="001001",
            supplier_category_name="패션의류/여성의류",
            marketplace="coupang",
        )

        # 11번가 매핑
        st11_result = mapper.get_marketplace_category(
            supplier_id="domeme",
            supplier_category_code="001001",
            supplier_category_name="패션의류/여성의류",
            marketplace="11st",
        )

        assert coupang_result is not None
        assert st11_result is not None
        assert coupang_result[0] != st11_result[0]  # 코드는 달라야 함

    def test_no_mapping_found(self, mapper):
        """매핑을 찾을 수 없는 경우"""
        result = mapper.get_marketplace_category(
            supplier_id="unknown",
            supplier_category_code="NOTFOUND",
            supplier_category_name="완전히 알 수 없는 카테고리",
            marketplace="unknown_market",
        )

        assert result is None

    def test_save_and_load_mappings(self, mapper):
        """매핑 저장 및 로드"""
        # 커스텀 매핑 추가
        mapper.add_mapping(
            CategoryMapping(
                supplier_code="SAVE_TEST",
                supplier_name="저장테스트",
                marketplace="coupang",
                marketplace_code="777777",
                marketplace_name="저장된카테고리",
                confidence=0.9,
            )
        )

        # 임시 파일에 저장
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            filepath = f.name

        mapper.save_mappings(filepath)

        # 새 매퍼에서 로드
        new_mapper = CategoryMapper()
        new_mapper.load_mappings(filepath)

        # 저장된 매핑이 로드되었는지 확인
        result = new_mapper.get_marketplace_category(
            supplier_id="domeme",
            supplier_category_code="SAVE_TEST",
            supplier_category_name="저장테스트",
            marketplace="coupang",
        )

        assert result is not None
        assert result[0] == "777777"
        assert result[2] == 0.9

        # 임시 파일 삭제
        Path(filepath).unlink()

    def test_category_stats(self, mapper):
        """카테고리 통계"""
        # 추가 매핑
        for i in range(5):
            mapper.add_mapping(
                CategoryMapping(
                    supplier_code=f"STAT{i}",
                    supplier_name=f"통계테스트{i}",
                    marketplace="coupang" if i < 3 else "11st",
                    marketplace_code=f"88888{i}",
                    marketplace_name=f"통계카테고리{i}",
                )
            )

        stats = mapper.get_stats()

        assert stats["total_mappings"] > 5  # 기본 매핑 + 추가 매핑
        assert "domeme" in stats["by_supplier"]
        assert "coupang" in stats["by_marketplace"]
        assert "11st" in stats["by_marketplace"]

    def test_complex_category_name(self, mapper):
        """복잡한 카테고리명 처리"""
        # 다중 계층 카테고리
        result = mapper.get_marketplace_category(
            supplier_id="domeme",
            supplier_category_code="COMPLEX",
            supplier_category_name="가전/디지털/스마트폰/액세서리",
            marketplace="coupang",
        )

        assert result is not None
        # 전자제품 카테고리로 매칭되어야 함
        assert result[1] == "전자제품"

    def test_confidence_levels(self, mapper):
        """신뢰도 수준 테스트"""
        # 정확한 매칭 (신뢰도 1.0)
        exact = mapper.get_marketplace_category(
            supplier_id="domeme",
            supplier_category_code="001001",
            supplier_category_name="패션의류/여성의류",
            marketplace="coupang",
        )
        assert exact[2] == 1.0

        # 키워드 매칭 (신뢰도 < 1.0)
        keyword = mapper.get_marketplace_category(
            supplier_id="unknown",
            supplier_category_code="unknown",
            supplier_category_name="여성복",
            marketplace="coupang",
        )
        assert 0 < keyword[2] < 1.0
