#!/usr/bin/env python3
"""
드랍쉬핑 자동화 워크플로우 데모
오너클랜 상품 수집 → AI 가공 → 데이터베이스 저장
"""

import asyncio
import json
from datetime import datetime

from dotenv import load_dotenv
from dropshipping.monitoring.logger import get_logger
from dropshipping.storage.supabase_storage import SupabaseStorage
from dropshipping.suppliers.ownerclan.fetcher import OwnerclanFetcher
from dropshipping.suppliers.ownerclan.parser import OwnerclanParser
from dropshipping.suppliers.ownerclan.transformer import OwnerclanTransformer
from dropshipping.ai_processors.product_enhancer import ProductEnhancer
from dropshipping.ai_processors.model_router import ModelRouter, TaskType

load_dotenv()
logger = get_logger(__name__)


async def main():
    """메인 워크플로우"""
    try:
        logger.info("="*60)
        logger.info("드랍쉬핑 자동화 워크플로우 데모 시작")
        logger.info("="*60)
        
        # 1. Storage 초기화
        logger.info("\n1. Supabase Storage 초기화...")
        storage = SupabaseStorage()
        logger.info("✅ Storage 준비 완료")
        
        # 2. 오너클랜 Fetcher 초기화
        logger.info("\n2. 오너클랜 Fetcher 초기화...")
        fetcher = OwnerclanFetcher(
            storage=storage,
            supplier_name="ownerclan",
            username="b00679540",
            password="ehdgod1101*",
            api_url="https://api.ownerclan.com/v1/graphql"
        )
        logger.info("✅ Fetcher 준비 완료")
        
        # 3. 상품 목록 조회 (최대 3개)
        logger.info("\n3. 오너클랜 상품 목록 조회 중...")
        raw_products = fetcher.fetch_list(page=1)[:3]  # 데모를 위해 3개만
        logger.info(f"✅ {len(raw_products)}개 상품 조회 완료")
        
        # 디버깅: 첫 번째 상품 출력
        if raw_products:
            logger.info(f"첫 번째 상품: {json.dumps(raw_products[0], indent=2, ensure_ascii=False)}")
        
        if not raw_products:
            logger.warning("조회된 상품이 없습니다.")
            return
            
        # 4. 상품 상세 정보 조회 (Parser 사용)
        logger.info("\n4. 상품 상세 정보 조회 중...")
        parser = OwnerclanParser()
        parsed_products = []
        
        for product in raw_products:
            # 각 상품의 상세 정보 조회
            try:
                detail = fetcher.fetch_detail(product['key'])
                logger.info(f"  상세 조회 결과: {bool(detail)}")
                if detail:
                    logger.info(f"  Detail type: {type(detail)}, keys: {list(detail.keys()) if isinstance(detail, dict) else 'Not a dict'}")
                if detail:
                    # detail이 이미 item 데이터이므로 직접 _parse_node 호출
                    parsed = parser._parse_node(detail)
                    logger.info(f"  파싱 결과: {bool(parsed)}")
                    if parsed:
                        parsed_products.append(parsed)
                        logger.info(f"  - {parsed.get('name', 'Unknown')[:30]}... 파싱 완료")
            except Exception as e:
                logger.error(f"  상품 {product['key']} 처리 중 오류: {str(e)}")
        
        logger.info(f"✅ {len(parsed_products)}개 상품 파싱 완료")
        
        # 5. Transformer로 표준 형식 변환
        logger.info("\n5. 표준 상품 형식으로 변환 중...")
        transformer = OwnerclanTransformer()
        standard_products = []
        
        for parsed in parsed_products:
            standard = transformer.to_standard(parsed)
            if standard:
                standard_products.append(standard)
                logger.info(f"  - {standard.name[:30]}... 변환 완료")
        
        logger.info(f"✅ {len(standard_products)}개 상품 변환 완료")
        
        # 6. AI 가공 (첫 번째 상품만 데모)
        if standard_products:
            logger.info("\n6. AI 상품 가공 시작...")
            
            # Gemini API 키 설정
            import os
            os.environ['GOOGLE_API_KEY'] = os.getenv('GEMINI_API_KEY')
            
            # Model Router 초기화 - Gemini 모델만 사용하도록 설정
            from dropshipping.ai_processors.model_router import ModelRouter, ModelProvider, ModelConfig
            from decimal import Decimal
            
            model_router = ModelRouter()
            
            # Ollama 모델들을 Gemini로 대체
            model_router.models = {
                "gemini-flash-mini": ModelConfig(
                    provider=ModelProvider.GEMINI,
                    model_name="gemini-1.5-flash",
                    max_tokens=8192,
                    temperature=0.7,
                    cost_per_1k_tokens=Decimal("0.0001"),
                    supports_vision=True,
                    context_window=65536,
                ),
                "gemini-flash": ModelConfig(
                    provider=ModelProvider.GEMINI,
                    model_name="gemini-1.5-flash",
                    max_tokens=8192,
                    temperature=0.7,
                    cost_per_1k_tokens=Decimal("0.0003"),
                    supports_vision=True,
                    context_window=131072,
                ),
            }
            
            # 모든 작업을 Gemini로 매핑
            for task_type in TaskType:
                model_router.task_model_mapping[task_type] = "gemini-flash-mini"
            
            # Product Enhancer 초기화
            enhancer = ProductEnhancer(model_router=model_router)
            
            # 첫 번째 상품 가공
            product = standard_products[0]
            logger.info(f"\n처리 중: {product.name}")
            logger.info(f"원본 설명: {product.description[:100]}...")
            
            # AI 처리
            enhanced_result = await enhancer.process(product)
            
            if enhanced_result and enhanced_result.get('enhancements'):
                logger.info(f"\n✅ AI 가공 완료!")
                enhancements = enhanced_result['enhancements']
                
                # 개선된 이름
                if 'enhanced_name' in enhancements:
                    logger.info(f"개선된 이름: {enhancements['enhanced_name']}")
                    product.name = enhancements['enhanced_name']
                
                # 생성된 설명
                if 'generated_description' in enhancements:
                    logger.info(f"개선된 설명: {enhancements['generated_description'][:200]}...")
                    product.description = enhancements['generated_description']
                
                # SEO 키워드
                if 'seo_keywords' in enhancements:
                    logger.info(f"생성된 태그: {', '.join(enhancements['seo_keywords'][:5])}")
                    product.tags = enhancements['seo_keywords']
                
                # 7. 데이터베이스 저장
                logger.info("\n7. 데이터베이스 저장 중...")
                
                # products_processed 테이블에 저장
                product_data = product.model_dump(mode='json')
                product_data['supplier_id'] = 'ownerclan'
                product_data['created_at'] = datetime.now().isoformat()
                product_data['ai_enhanced'] = True
                product_data['ai_enhancements'] = enhanced_result
                
                result = storage.client.table('products_processed').insert(product_data).execute()
                
                if result.data:
                    logger.info(f"✅ 데이터베이스 저장 성공! ID: {result.data[0].get('id')}")
                else:
                    logger.error("데이터베이스 저장 실패")
            else:
                logger.error("AI 가공 실패")
        
        logger.info("\n" + "="*60)
        logger.info("워크플로우 완료!")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"워크플로우 실행 중 오류: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())