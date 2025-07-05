"""
마켓플레이스 업로더 사용 예제
"""

import asyncio
from decimal import Decimal
from pathlib import Path
import os

from dropshipping.models.product import StandardProduct, ProductImage, ProductVariant
from dropshipping.storage.supabase_storage import SupabaseStorage
from dropshipping.uploader.coupang_api.coupang_uploader import CoupangUploader
from dropshipping.uploader.gmarket_excel.gmarket_excel_uploader import GmarketExcelUploader
from dropshipping.uploader.base import MarketplaceType


async def upload_to_coupang():
    """쿠팡에 상품 업로드 예제"""
    
    # 저장소 초기화
    storage = SupabaseStorage(
        url=os.getenv("SUPABASE_URL", "https://fake.supabase.co"),
        key=os.getenv("SUPABASE_KEY", "fake-key")
    )
    
    # 쿠팡 업로더 설정
    config = {
        "api_key": os.getenv("COUPANG_ACCESS_KEY", "test_key"),
        "api_secret": os.getenv("COUPANG_SECRET_KEY", "test_secret"),
        "vendor_id": "A00000000",
        "test_mode": True,  # 테스트 모드
        "return_center_code": "1000274592",
        "shipping_place_code": "74010"
    }
    
    uploader = CoupangUploader(storage=storage, config=config)
    
    # 테스트 상품 생성
    product = StandardProduct(
        id="test-product-001",
        supplier_id="domeme",
        supplier_product_id="DM12345",
        name="[공식] 블루투스 이어폰 5.3 무선 충전 노이즈캔슬링",
        description="최신 블루투스 5.3 기술을 적용한 프리미엄 무선 이어폰",
        price=Decimal("39900"),
        cost=Decimal("25000"),
        category_name="전자기기/이어폰",
        stock=100,
        brand="TestBrand",
        images=[
            ProductImage(
                url="https://example.com/earphone_main.jpg",
                is_main=True
            ),
            ProductImage(
                url="https://example.com/earphone_detail1.jpg",
                is_main=False
            )
        ],
        variants=[
            ProductVariant(
                sku="test-001-black",
                options={"색상": "블랙"},
                price=Decimal("39900"),
                stock=50
            ),
            ProductVariant(
                sku="test-001-white",
                options={"색상": "화이트"},
                price=Decimal("39900"),
                stock=50
            )
        ],
        attributes={
            "shipping_fee": 2500,
            "model": "TWS-PRO-2024",
            "manufacturer": "테스트 제조사"
        }
    )
    
    # 단일 상품 업로드
    print("쿠팡 업로드 시작...")
    result = await uploader.upload_product(product)
    
    if result["status"].value == "success":
        print(f"✅ 업로드 성공! 상품 ID: {result['marketplace_product_id']}")
    else:
        print(f"❌ 업로드 실패: {result['errors']}")
    
    # 통계 출력
    stats = uploader.get_stats()
    print(f"\n📊 업로드 통계:")
    print(f"  - 성공: {stats['uploaded']}")
    print(f"  - 실패: {stats['failed']}")
    print(f"  - 성공률: {stats['success_rate']:.1%}")


async def batch_upload_to_gmarket():
    """G마켓 Excel 배치 업로드 예제"""
    
    # 저장소 초기화
    storage = SupabaseStorage(
        url=os.getenv("SUPABASE_URL", "https://fake.supabase.co"),
        key=os.getenv("SUPABASE_KEY", "fake-key")
    )
    
    # Excel 출력 디렉터리
    output_dir = Path("./excel_output")
    output_dir.mkdir(exist_ok=True)
    
    # G마켓 업로더 설정
    config = {
        "output_dir": str(output_dir),
        "marketplace": "gmarket",
        "seller_code": "TEST_SELLER",
        "shipping_address": "서울특별시 강남구 테헤란로 123",
        "return_address": "서울특별시 강남구 반품센터"
    }
    
    uploader = GmarketExcelUploader(storage=storage, config=config)
    
    # 여러 상품 준비
    products = [
        StandardProduct(
            id=f"gm-product-{i:03d}",
            supplier_id="domeme",
            supplier_product_id=f"DM{i:05d}",
            name=f"테스트 상품 {i} - 블루투스 이어폰",
            description=f"상품 {i}번 설명입니다.",
            price=Decimal(str(20000 + i * 1000)),
            cost=Decimal(str(15000 + i * 500)),
            category_name="전자기기/이어폰",
            stock=100 + i * 10,
            brand="TestBrand",
            images=[
                ProductImage(
                    url=f"https://example.com/product_{i}_main.jpg",
                    is_main=True
                )
            ],
            attributes={
                "manufacturer": "테스트 제조사"
            }
        )
        for i in range(1, 6)
    ]
    
    # 배치 업로드
    print("G마켓 Excel 배치 업로드 시작...")
    results = await uploader.upload_batch(products)
    
    # 결과 출력
    success_count = sum(1 for r in results if r["status"].value == "success")
    print(f"\n✅ 업로드 완료: {success_count}/{len(products)} 성공")
    
    # Excel 파일 위치 출력
    for result in results:
        if result["status"].value == "success" and "excel_file" in result:
            print(f"📄 Excel 파일: {output_dir / result['excel_file']}")
            break
    
    # 실패한 상품 출력
    failed = [r for r in results if r["status"].value == "failed"]
    if failed:
        print("\n❌ 실패한 상품:")
        for f in failed:
            print(f"  - {f['product_id']}: {f['errors']}")


async def main():
    """메인 실행 함수"""
    print("=== 마켓플레이스 업로더 예제 ===\n")
    
    # 쿠팡 업로드 예제
    print("1. 쿠팡 단일 상품 업로드")
    print("-" * 40)
    await upload_to_coupang()
    
    print("\n")
    
    # G마켓 배치 업로드 예제
    print("2. G마켓 Excel 배치 업로드")
    print("-" * 40)
    await batch_upload_to_gmarket()
    
    print("\n✨ 모든 업로드 완료!")


if __name__ == "__main__":
    # 비동기 실행
    asyncio.run(main())