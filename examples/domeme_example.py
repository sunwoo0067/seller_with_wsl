"""
도매매(Domeme) API 사용 예제
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from loguru import logger

from dropshipping.suppliers.domeme import DomemeFetcher
from dropshipping.storage.json_storage import JSONStorage
from dropshipping.domain.pricing import PricingCalculator
from dropshipping.domain.validator import ProductValidator

# 환경 변수 로드
load_dotenv()


def main():
    """도매매 데이터 수집 예제"""
    
    # 1. 저장소 초기화
    storage = JSONStorage(base_path="./data/domeme_example")
    logger.info("JSON 저장소 초기화 완료")
    
    # 2. 도매매 수집기 초기화
    fetcher = DomemeFetcher(storage=storage)
    logger.info("도매매 수집기 초기화 완료")
    
    # API 연결 테스트
    if fetcher.client.check_connection():
        logger.success("도매매 API 연결 성공!")
    else:
        logger.error("도매매 API 연결 실패. API 키를 확인해주세요.")
        return
    
    # 3. 카테고리 001(패션의류)의 첫 페이지 수집
    logger.info("카테고리 001(패션의류) 상품 수집 시작...")
    fetcher.run_incremental(max_pages=1, category="001")
    
    # 4. 수집 통계 출력
    stats = fetcher.stats
    logger.info(f"수집 통계: {stats}")
    
    # 5. 저장된 상품 확인
    saved_products = storage.list_raw_products(supplier_id="domeme", limit=5)
    logger.info(f"저장된 상품 {len(saved_products)}개 확인")
    
    if saved_products:
        # 6. 첫 번째 상품에 대해 가격 계산
        logger.info("\n=== 가격 계산 예제 ===")
        pricing_calc = PricingCalculator()
        
        first_product = saved_products[0]["raw_json"]
        pricing_result = pricing_calc.calculate_price({
            "cost": first_product.get("supplyPrice", 0),
            "shipping_fee": first_product.get("deliveryPrice", 0),
            "category_code": first_product.get("category1"),
        })
        
        logger.info(f"상품명: {first_product.get('productNm')}")
        logger.info(f"원가: {pricing_result['cost']:,}원")
        logger.info(f"계산된 판매가: {pricing_result['final_price']:,}원")
        logger.info(f"마진액: {pricing_result['margin_amount']:,}원")
        logger.info(f"마진율: {float(pricing_result['margin_rate']):.1%}")
        logger.info(f"적용 규칙: {pricing_result['applied_rule']}")
        
        # 7. 상품 검증
        logger.info("\n=== 상품 검증 예제 ===")
        validator = ProductValidator()
        
        # 처리된 상품이 있는지 확인
        processed_products = storage.list_raw_products(
            supplier_id="domeme", 
            status="processed",
            limit=1
        )
        
        if processed_products:
            # 처리된 상품 검증
            processed = storage.get_processed_product(processed_products[0]["id"])
            if processed:
                validation_result = validator.validate_product(processed, marketplace="coupang")
                
                logger.info(f"검증 결과: {'유효' if validation_result.is_valid else '무효'}")
                logger.info(f"품질 점수: {validation_result.score:.1%}")
                
                if validation_result.errors:
                    logger.warning(f"오류 {len(validation_result.errors)}개:")
                    for error in validation_result.errors[:3]:  # 처음 3개만
                        logger.warning(f"  - {error['field']}: {error['message']}")
                        
                if validation_result.warnings:
                    logger.info(f"경고 {len(validation_result.warnings)}개:")
                    for warning in validation_result.warnings[:3]:  # 처음 3개만
                        logger.info(f"  - {warning['field']}: {warning['message']}")
    
    # 8. 전체 통계
    logger.info("\n=== 전체 통계 ===")
    total_stats = storage.get_stats()
    logger.info(f"총 원본 상품: {total_stats['total_raw']}개")
    logger.info(f"처리 완료: {total_stats['total_processed']}개")
    
    logger.success("도매매 API 예제 실행 완료!")


if __name__ == "__main__":
    main()