#!/usr/bin/env python3
"""
드랍쉬핑 자동화 시스템 통합 테스트
전체 파이프라인 (Fetcher -> Transformer -> CategoryMapper -> PricingEngine) 테스트
"""

import os
import sys
import asyncio
from decimal import Decimal
from pathlib import Path

# 프로젝트 루트 디렉터리를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dropshipping.suppliers.mock.mock_fetcher import MockFetcher
from dropshipping.transformers.domeme import DomemeTransformer
from dropshipping.transformers.category_mapper import CategoryMapper
from dropshipping.transformers.pricing_engine import PricingEngine
from dropshipping.models.product import StandardProduct

from loguru import logger


class IntegrationTestRunner:
    """통합 테스트 실행기"""

    def __init__(self):
        """초기화"""
        self.test_data_dir = project_root / "test_data"
        self.test_data_dir.mkdir(exist_ok=True)
        
        # 컴포넌트 초기화
        self.fetcher = MockFetcher()
        self.transformer = DomemeTransformer()
        self.category_mapper = CategoryMapper(data_dir=self.test_data_dir / "categories")
        self.pricing_engine = PricingEngine(data_dir=self.test_data_dir / "pricing")
        
        # 테스트 결과
        self.test_results = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "errors": []
        }

    def run_all_tests(self):
        """모든 통합 테스트 실행"""
        logger.info("🚀 드랍쉬핑 자동화 시스템 통합 테스트 시작")
        
        # 개별 컴포넌트 테스트
        self.test_fetcher_component()
        self.test_transformer_component()
        self.test_category_mapper_component()
        self.test_pricing_engine_component()
        
        # 통합 파이프라인 테스트
        self.test_full_pipeline()
        self.test_batch_processing()
        self.test_error_handling()
        
        # 결과 출력
        self.print_test_results()

    def test_fetcher_component(self):
        """Fetcher 컴포넌트 테스트"""
        logger.info("📥 Fetcher 컴포넌트 테스트")
        
        try:
            # 상품 목록 조회
            products, has_next = self.fetcher.fetch_list(page=1)
            self.assert_test(len(products) > 0, "상품 목록 조회 성공")
            self.assert_test(isinstance(has_next, bool), "페이지네이션 정보 반환")
            
            # 상품 상세 조회
            if products:
                product_id = products[0]["productNo"]
                detail = self.fetcher.fetch_detail(product_id)
                self.assert_test(detail is not None, "상품 상세 정보 조회 성공")
                self.assert_test("productNm" in detail, "상품명 정보 포함")
                self.assert_test("supplyPrice" in detail, "가격 정보 포함")
            
            logger.success("✅ Fetcher 컴포넌트 테스트 완료")
            
        except Exception as e:
            self.record_error("Fetcher 컴포넌트 테스트 실패", e)

    def test_transformer_component(self):
        """Transformer 컴포넌트 테스트"""
        logger.info("🔄 Transformer 컴포넌트 테스트")
        
        try:
            # Mock 데이터 생성
            mock_data = {
                "productNo": "TEST001",
                "productName": "테스트 상품",
                "price": "10000",
                "consumerPrice": "15000",
                "stockQuantity": "100",
                "brandName": "테스트 브랜드",
                "category1Name": "패션의류",
                "mainImage": "https://example.com/image.jpg"
            }
            
            # 변환 테스트
            standard_product = self.transformer.to_standard(mock_data)
            self.assert_test(standard_product is not None, "데이터 변환 성공")
            self.assert_test(isinstance(standard_product, StandardProduct), "StandardProduct 객체 생성")
            self.assert_test(standard_product.name == "테스트 상품", "상품명 변환 정확")
            self.assert_test(standard_product.cost == Decimal("10000"), "가격 변환 정확")
            
            logger.success("✅ Transformer 컴포넌트 테스트 완료")
            
        except Exception as e:
            self.record_error("Transformer 컴포넌트 테스트 실패", e)

    def test_category_mapper_component(self):
        """CategoryMapper 컴포넌트 테스트"""
        logger.info("🏷️ CategoryMapper 컴포넌트 테스트")
        
        try:
            # 카테고리 매핑 테스트
            standard_code, confidence = self.category_mapper.map_supplier_category(
                "domeme", "001", "패션의류"
            )
            self.assert_test(standard_code is not None, "카테고리 매핑 성공")
            self.assert_test(confidence > 0, "매핑 신뢰도 반환")
            
            # 마켓플레이스 매핑 테스트
            marketplace_code = self.category_mapper.get_marketplace_category(
                standard_code, "smartstore"
            )
            self.assert_test(marketplace_code is not None, "마켓플레이스 매핑 성공")
            
            # 키워드 기반 매핑 테스트
            keyword_code, keyword_confidence = self.category_mapper.map_supplier_category(
                "unknown", "999", "여성 블라우스"
            )
            self.assert_test(keyword_code is not None, "키워드 기반 매핑 성공")
            
            logger.success("✅ CategoryMapper 컴포넌트 테스트 완료")
            
        except Exception as e:
            self.record_error("CategoryMapper 컴포넌트 테스트 실패", e)

    def test_pricing_engine_component(self):
        """PricingEngine 컴포넌트 테스트"""
        logger.info("💰 PricingEngine 컴포넌트 테스트")
        
        try:
            # 기본 가격 계산
            cost = Decimal("10000")
            result = self.pricing_engine.calculate_price(cost)
            self.assert_test(result.final_price > cost, "가격 계산 성공")
            self.assert_test(result.margin_rate > 0, "마진율 계산 정확")
            
            # 카테고리별 가격 계산
            fashion_result = self.pricing_engine.calculate_price(
                cost, category_code="FASHION"
            )
            self.assert_test(fashion_result.final_price > cost, "패션 카테고리 가격 계산")
            
            # 공급사별 가격 계산
            domeme_result = self.pricing_engine.calculate_price(
                cost, supplier_id="domeme"
            )
            self.assert_test(domeme_result.final_price > cost, "도매매 공급사 가격 계산")
            
            logger.success("✅ PricingEngine 컴포넌트 테스트 완료")
            
        except Exception as e:
            self.record_error("PricingEngine 컴포넌트 테스트 실패", e)

    def test_full_pipeline(self):
        """전체 파이프라인 테스트"""
        logger.info("🔗 전체 파이프라인 테스트")
        
        try:
            # 1. 데이터 수집
            products, _ = self.fetcher.fetch_list(page=1)
            self.assert_test(len(products) > 0, "1단계: 데이터 수집 성공")
            
            # 첫 번째 상품으로 파이프라인 테스트
            raw_product = products[0]
            product_id = raw_product["productNo"]
            
            # 상세 정보 조회
            detail_data = self.fetcher.fetch_detail(product_id)
            self.assert_test(detail_data is not None, "상세 정보 조회 성공")
            
            # 2. 데이터 변환
            standard_product = self.transformer.to_standard(detail_data)
            self.assert_test(standard_product is not None, "2단계: 데이터 변환 성공")
            
            # 3. 카테고리 매핑
            category_code, confidence = self.category_mapper.map_supplier_category(
                "domeme",
                standard_product.category_code,
                standard_product.category_name,
                standard_product.name
            )
            self.assert_test(category_code is not None, "3단계: 카테고리 매핑 성공")
            
            # 표준 카테고리 적용
            standard_product.category_code = category_code
            
            # 4. 가격 책정
            pricing_result = self.pricing_engine.calculate_price(
                standard_product.cost,
                supplier_id=standard_product.supplier_id,
                category_code=standard_product.category_code,
                product_name=standard_product.name
            )
            self.assert_test(pricing_result.final_price > 0, "4단계: 가격 책정 성공")
            
            # 최종 가격 적용
            standard_product.price = pricing_result.final_price
            
            # 5. 마켓플레이스 매핑
            smartstore_category = self.category_mapper.get_marketplace_category(
                category_code, "smartstore"
            )
            self.assert_test(smartstore_category is not None, "5단계: 마켓플레이스 매핑 성공")
            
            # 파이프라인 결과 출력
            logger.info(f"📋 파이프라인 결과:")
            logger.info(f"  - 상품명: {standard_product.name}")
            logger.info(f"  - 원가: {standard_product.cost:,}원")
            logger.info(f"  - 판매가: {standard_product.price:,}원")
            logger.info(f"  - 마진율: {pricing_result.margin_rate:.1%}")
            logger.info(f"  - 카테고리: {category_code} (신뢰도: {confidence:.1%})")
            logger.info(f"  - 스마트스토어 카테고리: {smartstore_category}")
            
            logger.success("✅ 전체 파이프라인 테스트 완료")
            
        except Exception as e:
            self.record_error("전체 파이프라인 테스트 실패", e)

    def test_batch_processing(self):
        """배치 처리 테스트"""
        logger.info("📦 배치 처리 테스트")
        
        try:
            # 여러 상품 처리
            products, _ = self.fetcher.fetch_list(page=1)
            processed_count = 0
            error_count = 0
            
            for raw_product in products[:5]:  # 처음 5개 상품만 테스트
                try:
                    # 상세 정보 조회
                    detail_data = self.fetcher.fetch_detail(raw_product["productNo"])
                    if not detail_data:
                        continue
                    
                    # 변환
                    standard_product = self.transformer.to_standard(detail_data)
                    if not standard_product:
                        continue
                    
                    # 카테고리 매핑
                    category_code, _ = self.category_mapper.map_supplier_category(
                        "domeme",
                        standard_product.category_code,
                        standard_product.category_name
                    )
                    
                    # 가격 책정
                    pricing_result = self.pricing_engine.calculate_price(
                        standard_product.cost,
                        supplier_id=standard_product.supplier_id,
                        category_code=category_code
                    )
                    
                    processed_count += 1
                    
                except Exception as e:
                    error_count += 1
                    logger.warning(f"상품 처리 실패: {raw_product.get('productNo', 'Unknown')} - {e}")
            
            self.assert_test(processed_count > 0, f"배치 처리 성공: {processed_count}개 상품")
            self.assert_test(error_count < processed_count, f"오류율 허용 범위: {error_count}/{processed_count}")
            
            logger.success("✅ 배치 처리 테스트 완료")
            
        except Exception as e:
            self.record_error("배치 처리 테스트 실패", e)

    def test_error_handling(self):
        """오류 처리 테스트"""
        logger.info("⚠️ 오류 처리 테스트")
        
        try:
            # 잘못된 데이터 변환 테스트
            invalid_data = {"invalid": "data"}
            result = self.transformer.to_standard(invalid_data)
            self.assert_test(result is None, "잘못된 데이터 처리 성공")
            
            # 존재하지 않는 상품 조회 테스트
            try:
                self.fetcher.fetch_detail("NONEXISTENT_ID")
                self.assert_test(False, "존재하지 않는 상품 조회 시 오류 발생해야 함")
            except ValueError:
                self.assert_test(True, "존재하지 않는 상품 조회 오류 처리 성공")
            
            # 0원 가격 계산 테스트
            zero_result = self.pricing_engine.calculate_price(Decimal("0"))
            self.assert_test(zero_result.final_price >= 0, "0원 가격 계산 처리 성공")
            
            logger.success("✅ 오류 처리 테스트 완료")
            
        except Exception as e:
            self.record_error("오류 처리 테스트 실패", e)

    def assert_test(self, condition: bool, message: str):
        """테스트 결과 검증"""
        self.test_results["total_tests"] += 1
        
        if condition:
            self.test_results["passed_tests"] += 1
            logger.debug(f"✅ {message}")
        else:
            self.test_results["failed_tests"] += 1
            logger.error(f"❌ {message}")
            self.test_results["errors"].append(message)

    def record_error(self, message: str, error: Exception):
        """오류 기록"""
        self.test_results["failed_tests"] += 1
        error_msg = f"{message}: {str(error)}"
        self.test_results["errors"].append(error_msg)
        logger.error(error_msg)

    def print_test_results(self):
        """테스트 결과 출력"""
        logger.info("\n" + "="*60)
        logger.info("📊 통합 테스트 결과")
        logger.info("="*60)
        
        total = self.test_results["total_tests"]
        passed = self.test_results["passed_tests"]
        failed = self.test_results["failed_tests"]
        
        logger.info(f"총 테스트: {total}")
        logger.info(f"성공: {passed}")
        logger.info(f"실패: {failed}")
        
        if total > 0:
            success_rate = (passed / total) * 100
            logger.info(f"성공률: {success_rate:.1f}%")
        
        if failed > 0:
            logger.warning("\n실패한 테스트:")
            for error in self.test_results["errors"]:
                logger.warning(f"  - {error}")
        
        logger.info("="*60)
        
        if failed == 0:
            logger.success("🎉 모든 테스트가 성공했습니다!")
        else:
            logger.warning(f"⚠️ {failed}개의 테스트가 실패했습니다.")


def main():
    """메인 함수"""
    # 환경 변수 설정
    os.environ.setdefault("ENV", "test")
    os.environ.setdefault("CACHE_TTL", "3600")
    
    # 로그 설정
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        colorize=True
    )
    
    # 테스트 실행
    runner = IntegrationTestRunner()
    runner.run_all_tests()


if __name__ == "__main__":
    main() 