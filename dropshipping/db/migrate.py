"""
데이터베이스 마이그레이션 스크립트
JSONStorage에서 Supabase로 데이터 이전
"""

from datetime import datetime
from typing import Optional

import click
from loguru import logger
from tqdm import tqdm

from dropshipping.storage.json_storage import JSONStorage
from dropshipping.storage.supabase_storage import SupabaseStorage


class DataMigrator:
    """데이터 마이그레이션 도구"""

    def __init__(
        self,
        json_path: str = "./data",
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ):
        """
        Args:
            json_path: JSON 데이터 경로
            supabase_url: Supabase URL
            supabase_key: Supabase service key
        """
        # 저장소 초기화
        self.json_storage = JSONStorage(base_path=json_path)
        self.supabase_storage = SupabaseStorage(url=supabase_url, service_key=supabase_key)

        # 통계
        self.stats = {
            "raw_migrated": 0,
            "raw_failed": 0,
            "processed_migrated": 0,
            "processed_failed": 0,
        }

    def migrate_all(self, batch_size: int = 100):
        """전체 데이터 마이그레이션"""
        logger.info("데이터 마이그레이션 시작")
        start_time = datetime.now()

        # 1. 원본 데이터 마이그레이션
        self._migrate_raw_products(batch_size)

        # 2. 처리된 데이터 마이그레이션
        self._migrate_processed_products(batch_size)

        # 3. 결과 출력
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"마이그레이션 완료 (소요시간: {duration:.1f}초)")
        logger.info(
            f"원본 데이터: {self.stats['raw_migrated']}개 성공, {self.stats['raw_failed']}개 실패"
        )
        logger.info(
            f"처리된 데이터: {self.stats['processed_migrated']}개 성공, {self.stats['processed_failed']}개 실패"
        )

    def _migrate_raw_products(self, batch_size: int):
        """원본 상품 데이터 마이그레이션"""
        logger.info("원본 상품 데이터 마이그레이션 시작")

        # 전체 원본 데이터 가져오기
        offset = 0
        while True:
            raw_products = self.json_storage.list_raw_products(limit=batch_size, offset=offset)

            if not raw_products:
                break

            # 진행 표시
            with tqdm(total=len(raw_products), desc="원본 데이터") as pbar:
                for raw_data in raw_products:
                    try:
                        # 데이터 형식 조정
                        migration_data = {
                            "supplier_id": raw_data["supplier_id"],
                            "supplier_product_id": raw_data["supplier_product_id"],
                            "raw_json": raw_data["raw_json"],
                            "data_hash": raw_data["data_hash"],
                            "fetched_at": raw_data.get("fetched_at", raw_data.get("created_at")),
                        }

                        # Supabase에 저장
                        self.supabase_storage.save_raw_product(migration_data)
                        self.stats["raw_migrated"] += 1

                    except Exception as e:
                        logger.error(f"원본 데이터 마이그레이션 실패: {str(e)}")
                        self.stats["raw_failed"] += 1

                    pbar.update(1)

            offset += batch_size

    def _migrate_processed_products(self, batch_size: int):
        """처리된 상품 데이터 마이그레이션"""
        logger.info("처리된 상품 데이터 마이그레이션 시작")

        # JSON 저장소의 processed 데이터 가져오기
        all_raw = self.json_storage._raw_data
        processed_ids = list(self.json_storage._processed_data.keys())

        # 진행 표시
        with tqdm(total=len(processed_ids), desc="처리된 데이터") as pbar:
            for raw_id in processed_ids:
                try:
                    # 처리된 상품 가져오기
                    product = self.json_storage.get_processed_product(raw_id)
                    if not product:
                        continue

                    # 원본 데이터에서 Supabase raw_id 찾기
                    raw_record = all_raw.get(raw_id)
                    if not raw_record:
                        logger.warning(f"원본 데이터를 찾을 수 없습니다: {raw_id}")
                        continue

                    # Supabase에서 raw_id 조회
                    supabase_raw = (
                        self.supabase_storage.client.table("products_raw")
                        .select("id")
                        .eq(
                            "supplier_id",
                            self.supabase_storage._get_supplier_id(raw_record["supplier_id"]),
                        )
                        .eq("data_hash", raw_record["data_hash"])
                        .single()
                        .execute()
                    )

                    if not supabase_raw.data:
                        logger.warning(f"Supabase에서 원본 데이터를 찾을 수 없습니다: {raw_id}")
                        continue

                    # 처리된 상품 저장
                    self.supabase_storage.save_processed_product(supabase_raw.data["id"], product)
                    self.stats["processed_migrated"] += 1

                except Exception as e:
                    logger.error(f"처리된 데이터 마이그레이션 실패: {str(e)}")
                    self.stats["processed_failed"] += 1

                pbar.update(1)

    def verify_migration(self):
        """마이그레이션 검증"""
        logger.info("마이그레이션 검증 시작")

        # JSON 저장소 통계
        json_stats = self.json_storage.get_stats()
        logger.info(
            f"JSON Storage - 원본: {json_stats['total_raw']}, 처리됨: {json_stats['total_processed']}"
        )

        # Supabase 통계
        supabase_stats = self.supabase_storage.get_stats()
        logger.info(
            f"Supabase - 원본: {supabase_stats['total_raw']}, 처리됨: {supabase_stats['total_processed']}"
        )

        # 차이 확인
        raw_diff = json_stats["total_raw"] - supabase_stats["total_raw"]
        processed_diff = json_stats["total_processed"] - supabase_stats["total_processed"]

        if raw_diff == 0 and processed_diff == 0:
            logger.success("✅ 마이그레이션이 성공적으로 완료되었습니다!")
        else:
            logger.warning(f"⚠️  데이터 불일치 - 원본: {raw_diff}개, 처리됨: {processed_diff}개")


@click.command()
@click.option(
    "--json-path",
    default="./data",
    help="JSON 데이터 경로",
    type=click.Path(exists=True),
)
@click.option(
    "--supabase-url",
    envvar="SUPABASE_URL",
    help="Supabase 프로젝트 URL",
)
@click.option(
    "--supabase-key",
    envvar="SUPABASE_SERVICE_ROLE_KEY",
    help="Supabase service role key",
)
@click.option(
    "--batch-size",
    default=100,
    help="배치 크기",
    type=int,
)
@click.option(
    "--verify-only",
    is_flag=True,
    help="검증만 수행",
)
def main(
    json_path: str,
    supabase_url: Optional[str],
    supabase_key: Optional[str],
    batch_size: int,
    verify_only: bool,
):
    """JSONStorage에서 Supabase로 데이터 마이그레이션"""
    try:
        # 마이그레이터 생성
        migrator = DataMigrator(
            json_path=json_path,
            supabase_url=supabase_url,
            supabase_key=supabase_key,
        )

        if verify_only:
            # 검증만 수행
            migrator.verify_migration()
        else:
            # 마이그레이션 실행
            migrator.migrate_all(batch_size=batch_size)

            # 검증
            click.echo("\n")
            migrator.verify_migration()

    except Exception as e:
        logger.error(f"마이그레이션 실패: {str(e)}")
        raise click.ClickException(str(e))


if __name__ == "__main__":
    main()
