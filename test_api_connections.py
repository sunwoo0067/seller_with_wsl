#!/usr/bin/env python3
"""
API 연결 테스트 스크립트
각 API의 연결 상태를 확인합니다.
"""

import asyncio
import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from dropshipping.monitoring.logger import get_logger
from dropshipping.storage.supabase_storage import SupabaseStorage

# .env 파일 로드
load_dotenv()

logger = get_logger(__name__)


async def test_supabase():
    """Supabase 연결 테스트"""
    try:
        logger.info("Supabase 연결 테스트 시작...")
        storage = SupabaseStorage()
        
        # 간단한 쿼리 실행
        result = storage.client.table("suppliers").select("*").limit(1).execute()
        logger.info(f"✅ Supabase 연결 성공! 공급사 테이블 확인됨")
        return True
    except Exception as e:
        logger.error(f"❌ Supabase 연결 실패: {str(e)}")
        return False


async def test_gemini():
    """Google Gemini API 테스트"""
    try:
        logger.info("Google Gemini API 테스트 시작...")
        api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key or api_key == "your-gemini-api-key":
            logger.warning("⚠️ Gemini API 키가 설정되지 않았습니다")
            return False
            
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Hello, test")
        
        logger.info(f"✅ Gemini API 연결 성공!")
        return True
    except Exception as e:
        logger.error(f"❌ Gemini API 연결 실패: {str(e)}")
        return False


async def test_domeme():
    """도매매 API 테스트"""
    try:
        logger.info("도매매 API 테스트 시작...")
        from dropshipping.suppliers.domeme.client import DomemeClient
        
        client = DomemeClient(
            api_key=os.getenv("DOMEME_API_KEY")
        )
        
        # 연결 확인 (동기 메서드)
        if client.check_connection():
            logger.info(f"✅ 도매매 API 연결 성공!")
            return True
        else:
            logger.error("❌ 도매매 API 연결 실패")
            return False
    except Exception as e:
        logger.error(f"❌ 도매매 API 연결 실패: {str(e)}")
        return False


async def test_ownerclan():
    """오너클랜 API 테스트"""
    try:
        logger.info("오너클랜 API 테스트 시작...")
        from dropshipping.suppliers.ownerclan.fetcher import OwnerclanFetcher
        
        # Mock storage for testing
        class MockStorage:
            def save_raw_products(self, *args, **kwargs):
                return None
                
        fetcher = OwnerclanFetcher(
            storage=MockStorage(),
            supplier_name="ownerclan",
            username=os.getenv("OWNERCLAN_USERNAME"),
            password=os.getenv("OWNERCLAN_PASSWORD"),
            api_url="https://api.ownerclan.com/v1/graphql"
        )
        
        # 인증 테스트 (동기 메서드이므로 await 없이 호출)
        token = fetcher._get_token()
        if token:
            logger.info(f"✅ 오너클랜 API 인증 성공!")
            return True
        else:
            logger.error("❌ 오너클랜 API 인증 실패")
            return False
    except Exception as e:
        logger.error(f"❌ 오너클랜 API 연결 실패: {str(e)}")
        return False


async def test_coupang():
    """쿠팡 API 테스트"""
    try:
        logger.info("쿠팡 API 테스트 시작...")
        access_key = os.getenv("COUPANG_ACCESS_KEY")
        secret_key = os.getenv("COUPANG_SECRET_KEY")
        vendor_id = os.getenv("COUPANG_VENDOR_ID")
        
        if not all([access_key, secret_key, vendor_id]) or "your-" in access_key:
            logger.warning("⚠️ 쿠팡 API 키가 완전히 설정되지 않았습니다")
            return False
            
        # 실제 API 호출은 vendor_id 검증이 필요하므로 키 존재 여부만 확인
        logger.info(f"✅ 쿠팡 API 키 설정 확인됨 (Vendor ID: {vendor_id})")
        return True
    except Exception as e:
        logger.error(f"❌ 쿠팡 API 확인 실패: {str(e)}")
        return False


async def main():
    """모든 API 연결 테스트 실행"""
    logger.info("="*60)
    logger.info("API 연결 테스트 시작")
    logger.info("="*60)
    
    results = {}
    
    # 각 API 테스트
    results['Supabase'] = await test_supabase()
    results['Google Gemini'] = await test_gemini()
    results['도매매'] = await test_domeme()
    results['오너클랜'] = await test_ownerclan()
    results['쿠팡'] = await test_coupang()
    
    # 결과 요약
    logger.info("\n" + "="*60)
    logger.info("테스트 결과 요약")
    logger.info("="*60)
    
    for api_name, success in results.items():
        status = "✅ 성공" if success else "❌ 실패"
        logger.info(f"{api_name}: {status}")
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    logger.info(f"\n전체: {success_count}/{total_count} 성공")
    
    if success_count < total_count:
        logger.warning("\n⚠️ 일부 API 연결에 실패했습니다. .env 파일을 확인해주세요.")
    else:
        logger.info("\n🎉 모든 API 연결에 성공했습니다!")


if __name__ == "__main__":
    asyncio.run(main())