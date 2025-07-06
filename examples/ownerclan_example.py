"""
오너클랜 공급사 통합 예제
실제 API 호출을 통한 상품 수집 테스트
"""

import asyncio
import os
from dotenv import load_dotenv

from dropshipping.suppliers.ownerclan.fetcher import OwnerclanFetcher
from dropshipping.suppliers.ownerclan.parser import OwnerclanParser
from dropshipping.suppliers.ownerclan.transformer import OwnerclanTransformer
from dropshipping.storage.json_storage import JSONStorage
from dropshipping.monitoring.logger import get_logger

# 환경 변수 로드
load_dotenv()

logger = get_logger(__name__)


async def test_ownerclan_integration():
    """오너클랜 통합 테스트"""
    
    # 설정 확인
    username = os.getenv("OWNERCLAN_USERNAME")
    password = os.getenv("OWNERCLAN_PASSWORD")
    api_url = os.getenv("OWNERCLAN_API_URL", "https://api.ownerclan.com/v1/graphql")
    
    if not username or not password:
        logger.error("오너클랜 인증 정보가 설정되지 않았습니다.")
        logger.info("OWNERCLAN_USERNAME과 OWNERCLAN_PASSWORD를 .env 파일에 설정해주세요.")
        return
    
    # 저장소 초기화
    storage = JSONStorage("./data/ownerclan_test")
    
    # Fetcher, Parser, Transformer 초기화
    fetcher = OwnerclanFetcher(
        storage=storage,
        supplier_name="ownerclan",
        username=username,
        password=password,
        api_url=api_url
    )
    parser = OwnerclanParser()
    transformer = OwnerclanTransformer()
    
    try:
        # 1. 인증 테스트
        logger.info("오너클랜 인증 시도...")
        token = fetcher._get_token()
        logger.info(f"✅ 인증 성공! 토큰 길이: {len(token)}")
        
        # 2. 상품 목록 조회
        logger.info("상품 목록 조회 중...")
        products = fetcher.fetch_list(1)
        logger.info(f"조회된 상품 수: {len(products)}")
        
        if not products:
            logger.warning("조회된 상품이 없습니다.")
            return
        
        # 3. 첫 번째 상품 상세 조회
        first_product = products[0]
        product_id = first_product.get("key", "")
        
        logger.info(f"상품 상세 조회: {product_id}")
        detail = fetcher.fetch_detail(product_id)
        
        # 4. 파싱
        parsed = parser.parse_product_detail({"data": {"item": detail}})
        logger.info(f"파싱 완료: {parsed.get('name')}")
        
        # 5. 변환
        standard_product = transformer.transform(parsed)
        
        if standard_product:
            logger.info("✅ 표준 상품으로 변환 성공!")
            logger.info(f"  - 상품명: {standard_product.name}")
            logger.info(f"  - 브랜드: {standard_product.brand}")
            logger.info(f"  - 원가: {float(standard_product.cost):,}원")
            logger.info(f"  - 판매가: {float(standard_product.price):,}원")
            logger.info(f"  - 재고: {standard_product.stock}")
            logger.info(f"  - 옵션: {len(standard_product.options)}개")
            logger.info(f"  - 이미지: {len(standard_product.images)}개")
            
            # 6. 저장 (선택사항)
            # await storage.save_processed_products([standard_product])
            # logger.info("✅ 상품 저장 완료!")
        else:
            logger.error("상품 변환 실패")
            
    except Exception as e:
        logger.error(f"오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


async def test_bulk_fetch():
    """대량 상품 수집 테스트"""
    
    username = os.getenv("OWNERCLAN_USERNAME")
    password = os.getenv("OWNERCLAN_PASSWORD")
    api_url = os.getenv("OWNERCLAN_API_URL", "https://api.ownerclan.com/v1/graphql")
    
    if not username or not password:
        logger.error("오너클랜 인증 정보가 설정되지 않았습니다.")
        return
    
    storage = JSONStorage("./data/ownerclan_bulk")
    
    fetcher = OwnerclanFetcher(
        storage=storage,
        supplier_name="ownerclan",
        username=username,
        password=password,
        api_url=api_url
    )
    parser = OwnerclanParser()
    transformer = OwnerclanTransformer()
    
    try:
        # 여러 페이지 조회 (커서 기반이므로 현재는 첫 페이지만)
        all_products = []
        
        logger.info("대량 상품 수집 시작...")
        products = fetcher.fetch_list(1)
        
        for product in products[:5]:  # 처음 5개만 상세 조회
            product_id = product.get("key")
            if not product_id:
                continue
                
            logger.info(f"상품 상세 조회: {product_id}")
            detail = fetcher.fetch_detail(product_id)
            parsed = parser.parse_product_detail({"data": {"item": detail}})
            standard = transformer.transform(parsed)
            
            if standard:
                all_products.append(standard)
                
        logger.info(f"✅ 총 {len(all_products)}개 상품 수집 완료")
        
        # 저장
        if all_products:
            await storage.save_processed_products(all_products)
            logger.info("✅ 상품 저장 완료!")
            
    except Exception as e:
        logger.error(f"대량 수집 중 오류: {str(e)}")


if __name__ == "__main__":
    print("오너클랜 공급사 통합 테스트")
    print("=" * 50)
    
    # 기본 테스트 실행
    asyncio.run(test_ownerclan_integration())
    
    # 대량 수집 테스트 (주석 해제하여 실행)
    # print("\n대량 수집 테스트")
    # print("=" * 50)
    # asyncio.run(test_bulk_fetch())