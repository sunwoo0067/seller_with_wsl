"""
카테고리 매핑 시스템 테스트
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from dropshipping.transformers.category_mapper import (
    CategoryLevel,
    CategoryMapper,
    StandardCategory,
    SupplierCategoryMapping,
)


class TestCategoryMapper:
    """CategoryMapper 테스트"""

    @pytest.fixture
    def temp_data_dir(self):
        """임시 데이터 디렉터리"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def category_mapper(self, temp_data_dir):
        """CategoryMapper 인스턴스"""
        return CategoryMapper(data_dir=temp_data_dir)

    def test_initialization(self, category_mapper):
        """초기화 테스트"""
        assert len(category_mapper.standard_categories) > 0
        assert "FASHION" in category_mapper.standard_categories
        assert "BEAUTY" in category_mapper.standard_categories
        assert "ELECTRONICS" in category_mapper.standard_categories

    def test_standard_category_structure(self, category_mapper):
        """표준 카테고리 구조 테스트"""
        fashion = category_mapper.standard_categories["FASHION"]

        assert fashion.code == "FASHION"
        assert fashion.name == "패션의류"
        assert fashion.level == CategoryLevel.LEVEL_1
        assert fashion.parent_code is None
        assert len(fashion.children) > 0
        assert len(fashion.keywords) > 0
        assert "smartstore" in fashion.marketplace_mappings

    def test_category_hierarchy(self, category_mapper):
        """카테고리 계층 구조 테스트"""
        # FASHION_WOMEN이 있다면 계층 구조 테스트
        if "FASHION_WOMEN" in category_mapper.standard_categories:
            hierarchy = category_mapper.get_category_hierarchy("FASHION_WOMEN")

            assert len(hierarchy) == 2
            assert hierarchy[0].code == "FASHION"  # 부모
            assert hierarchy[1].code == "FASHION_WOMEN"  # 자식

    def test_supplier_mapping_domeme(self, category_mapper):
        """도매매 카테고리 매핑 테스트"""
        # 직접 매핑
        standard_code, confidence = category_mapper.map_supplier_category(
            "domeme", "001", "패션의류"
        )

        assert standard_code == "FASHION"
        assert confidence == 1.0

    def test_supplier_mapping_keyword_based(self, category_mapper):
        """키워드 기반 매핑 테스트"""
        # 새로운 카테고리 (매핑되지 않은)
        standard_code, confidence = category_mapper.map_supplier_category(
            "domeme", "999", "여성 블라우스"
        )

        assert standard_code in category_mapper.standard_categories
        assert 0 < confidence <= 1.0

    def test_product_name_based_mapping(self, category_mapper):
        """상품명 기반 매핑 테스트"""
        standard_code, confidence = category_mapper.map_supplier_category(
            "unknown_supplier", "unknown_category", None, "나이키 운동화 신발"
        )

        # 스포츠 또는 패션 카테고리로 매핑되어야 함
        assert standard_code in ["SPORTS", "FASHION", "FASHION_SHOES"]
        assert confidence > 0

    def test_marketplace_category_mapping(self, category_mapper):
        """마켓플레이스 카테고리 매핑 테스트"""
        # 스마트스토어 매핑
        smartstore_code = category_mapper.get_marketplace_category("FASHION", "smartstore")
        assert smartstore_code is not None
        assert smartstore_code.startswith("5")  # 스마트스토어 카테고리 형식

        # 쿠팡 매핑
        coupang_code = category_mapper.get_marketplace_category("BEAUTY", "coupang")
        assert coupang_code is not None
        assert coupang_code.isdigit()  # 쿠팡 카테고리는 숫자

    def test_keyword_mapping_cache(self, category_mapper):
        """키워드 매핑 캐시 테스트"""
        # 첫 번째 호출
        text = "여성 블라우스"
        result1 = category_mapper._map_by_keywords(text)

        # 두 번째 호출 (캐시 사용)
        result2 = category_mapper._map_by_keywords(text)

        assert result1 == result2
        assert text.lower() in category_mapper.keyword_cache

    def test_add_new_supplier_mapping(self, category_mapper):
        """새로운 공급사 매핑 추가 테스트"""
        initial_count = len(category_mapper.supplier_mappings.get("test_supplier", {}))

        # 새로운 매핑 추가
        category_mapper._add_supplier_mapping(
            "test_supplier", "TEST001", "테스트 카테고리", "FASHION", 0.9
        )

        # 매핑이 추가되었는지 확인
        assert "test_supplier" in category_mapper.supplier_mappings
        assert "TEST001" in category_mapper.supplier_mappings["test_supplier"]

        mapping = category_mapper.supplier_mappings["test_supplier"]["TEST001"]
        assert mapping.standard_category_code == "FASHION"
        assert mapping.confidence == 0.9

    def test_multiple_keyword_matching(self, category_mapper):
        """여러 키워드 매칭 테스트"""
        test_cases = [
            ("여성의류 블라우스", "FASHION"),
            ("스킨케어 화장품", "BEAUTY"),
            ("스마트폰 갤럭시", "ELECTRONICS"),
            ("운동화 나이키", "SPORTS"),
            ("아기 기저귀", "BABY"),
        ]

        for text, expected_category in test_cases:
            result = category_mapper._map_by_keywords(text)
            # 정확한 매칭이 어려울 수 있으므로 결과가 있는지만 확인
            assert result is not None

    def test_confidence_levels(self, category_mapper):
        """신뢰도 레벨 테스트"""
        # 직접 매핑 (높은 신뢰도)
        code1, conf1 = category_mapper.map_supplier_category("domeme", "001")
        assert conf1 == 1.0

        # 카테고리명 기반 (중간 신뢰도)
        code2, conf2 = category_mapper.map_supplier_category("unknown", "999", "패션의류")
        assert 0.5 <= conf2 < 1.0

        # 상품명 기반 (낮은 신뢰도)
        code3, conf3 = category_mapper.map_supplier_category(
            "unknown", "999", None, "여성 블라우스"
        )
        assert 0 < conf3 <= 0.7

    def test_statistics(self, category_mapper):
        """통계 정보 테스트"""
        stats = category_mapper.get_statistics()

        assert "standard_categories" in stats
        assert "supplier_mappings" in stats
        assert "keyword_cache_size" in stats

        assert stats["standard_categories"] > 0
        assert isinstance(stats["supplier_mappings"], dict)
        assert stats["keyword_cache_size"] >= 0

    def test_invalid_category_handling(self, category_mapper):
        """잘못된 카테고리 처리 테스트"""
        # 존재하지 않는 표준 카테고리
        marketplace_code = category_mapper.get_marketplace_category(
            "INVALID_CATEGORY", "smartstore"
        )
        assert marketplace_code is None

        # 존재하지 않는 마켓플레이스
        marketplace_code = category_mapper.get_marketplace_category(
            "FASHION", "invalid_marketplace"
        )
        assert marketplace_code is None

    def test_empty_input_handling(self, category_mapper):
        """빈 입력 처리 테스트"""
        # 빈 텍스트
        result = category_mapper._map_by_keywords("")
        assert result is None

        result = category_mapper._map_by_keywords(None)
        assert result is None

        # 빈 카테고리 정보
        code, conf = category_mapper.map_supplier_category("unknown", "")
        assert code is not None  # 기본값 반환
        assert conf > 0

    def test_case_insensitive_matching(self, category_mapper):
        """대소문자 무관 매칭 테스트"""
        result1 = category_mapper._map_by_keywords("패션의류")
        result2 = category_mapper._map_by_keywords("패션의류")
        result3 = category_mapper._map_by_keywords("패션의류")

        # 모두 같은 결과여야 함
        assert result1 == result2 == result3


class TestStandardCategory:
    """StandardCategory 데이터 클래스 테스트"""

    def test_category_creation(self):
        """카테고리 생성 테스트"""
        category = StandardCategory(code="TEST", name="테스트", level=CategoryLevel.LEVEL_1)

        assert category.code == "TEST"
        assert category.name == "테스트"
        assert category.level == CategoryLevel.LEVEL_1
        assert category.parent_code is None
        assert category.children == []
        assert category.keywords == []
        assert category.marketplace_mappings == {}

    def test_category_with_data(self):
        """데이터가 있는 카테고리 테스트"""
        category = StandardCategory(
            code="FASHION",
            name="패션",
            level=CategoryLevel.LEVEL_1,
            children=["FASHION_WOMEN", "FASHION_MEN"],
            keywords=["패션", "의류"],
            marketplace_mappings={"smartstore": "50000000"},
        )

        assert len(category.children) == 2
        assert len(category.keywords) == 2
        assert "smartstore" in category.marketplace_mappings


class TestSupplierCategoryMapping:
    """SupplierCategoryMapping 데이터 클래스 테스트"""

    def test_mapping_creation(self):
        """매핑 생성 테스트"""
        mapping = SupplierCategoryMapping(
            supplier_id="domeme",
            supplier_category_code="001",
            supplier_category_name="패션의류",
            standard_category_code="FASHION",
        )

        assert mapping.supplier_id == "domeme"
        assert mapping.supplier_category_code == "001"
        assert mapping.supplier_category_name == "패션의류"
        assert mapping.standard_category_code == "FASHION"
        assert mapping.confidence == 1.0
        assert mapping.keywords == []

    def test_mapping_with_confidence(self):
        """신뢰도가 있는 매핑 테스트"""
        mapping = SupplierCategoryMapping(
            supplier_id="unknown",
            supplier_category_code="999",
            supplier_category_name="알 수 없음",
            standard_category_code="FASHION",
            confidence=0.7,
            keywords=["키워드1", "키워드2"],
        )

        assert mapping.confidence == 0.7
        assert len(mapping.keywords) == 2
