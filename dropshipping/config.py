"""
설정 관리 모듈
환경 변수를 읽어 Pydantic 모델로 변환하여 타입 안전성 보장
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings

# .env 파일 로드 (명시적 경로 및 오버라이드)
load_dotenv(dotenv_path=".env", override=True)


class SupabaseConfig(BaseSettings):
    """Supabase 설정"""

    url: str = Field(..., env="SUPABASE_URL")
    service_role_key: str = Field(..., env="SUPABASE_SERVICE_ROLE_KEY")

    model_config = ConfigDict(env_prefix="SUPABASE_")


class DomemeConfig(BaseSettings):
    """도매매 API 설정"""

    api_key: str = Field(..., env="DOMEME_API_KEY")
    api_url: str = Field(default="https://openapi.domeggook.com")

    model_config = ConfigDict(env_prefix="DOMEME_")


class OwnerclanConfig(BaseSettings):
    """오너클랜 API 설정"""

    username: str = Field(..., env="OWNERCLAN_USERNAME")
    password: str = Field(..., env="OWNERCLAN_PASSWORD")
    api_url: str = Field(default="https://api.ownerclan.com/v1/graphql", env="OWNERCLAN_API_URL")

    model_config = ConfigDict(env_prefix="OWNERCLAN_")


class CoupangConfig(BaseSettings):
    """쿠팡 API 설정"""

    access_key: str = Field(..., env="COUPANG_ACCESS_KEY")
    secret_key: str = Field(..., env="COUPANG_SECRET_KEY")
    vendor_id: str = Field(..., env="COUPANG_VENDOR_ID")

    model_config = ConfigDict(env_prefix="COUPANG_")


class AIConfig(BaseSettings):
    """AI 모델 설정"""

    gemini_api_key: Optional[str] = Field(None, env="GEMINI_API_KEY")
    ollama_host: str = Field(default="http://localhost:11434", env="OLLAMA_HOST")

    model_config = ConfigDict(env_prefix="")


class MonitoringConfig(BaseSettings):
    """모니터링 설정"""

    slack_webhook_url: Optional[str] = Field(None, env="SLACK_WEBHOOK_URL")

    model_config = ConfigDict(env_prefix="")


class Settings(BaseSettings):
    """전체 애플리케이션 설정"""

    # 환경
    env: Literal["development", "staging", "production", "test"] = Field(
        default="development", env="ENV"
    )
    debug: bool = Field(default=False, env="DEBUG")
    dry_run: bool = Field(default=False, env="DRY_RUN")

    # 로깅
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: Optional[Path] = Field(default=None, env="LOG_FILE")

    # 스케줄러
    scheduler_enabled: bool = Field(default=False, env="SCHEDULER_ENABLED")
    scheduler_timezone: str = Field(default="Asia/Seoul", env="SCHEDULER_TIMEZONE")

    # 캐시
    cache_enabled: bool = Field(default=True, env="CACHE_ENABLED")
    cache_ttl: int = Field(default=3600, env="CACHE_TTL")

    # 파일 경로
    local_data_path: Path = Field(default=Path("./data"), env="LOCAL_DATA_PATH")
    local_upload_path: Path = Field(default=Path("./uploads"), env="LOCAL_UPLOAD_PATH")

    # 하위 설정 (선택적)
    _supabase: Optional[SupabaseConfig] = None
    _domeme: Optional[DomemeConfig] = None
    _ownerclan: Optional[OwnerclanConfig] = None
    _coupang: Optional[CoupangConfig] = None
    _ai: Optional[AIConfig] = None
    _monitoring: Optional[MonitoringConfig] = None

    model_config = ConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    @field_validator("log_file", mode="before")
    @classmethod
    def create_log_path(cls, v):
        if v:
            path = Path(v)
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        return v

    @field_validator("local_data_path", "local_upload_path", mode="before")
    @classmethod
    def create_paths(cls, v):
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def supabase(self) -> Optional[SupabaseConfig]:
        """Supabase 설정 (lazy loading)"""
        if self._supabase is None:
            try:
                self._supabase = SupabaseConfig()
            except:
                pass
        return self._supabase

    @property
    def domeme(self) -> Optional[DomemeConfig]:
        """도매매 설정 (lazy loading)"""
        if self._domeme is None:
            try:
                self._domeme = DomemeConfig()
            except:
                pass
        return self._domeme

    @property
    def ownerclan(self) -> Optional[OwnerclanConfig]:
        """오너클랜 설정 (lazy loading)"""
        if self._ownerclan is None:
            try:
                self._ownerclan = OwnerclanConfig()
            except:
                pass
        return self._ownerclan

    @property
    def coupang(self) -> Optional[CoupangConfig]:
        """쿠팡 설정 (lazy loading)"""
        if self._coupang is None:
            try:
                self._coupang = CoupangConfig()
            except:
                pass
        return self._coupang

    @property
    def ai(self) -> AIConfig:
        """AI 설정"""
        if self._ai is None:
            self._ai = AIConfig()
        return self._ai

    @property
    def monitoring(self) -> MonitoringConfig:
        """모니터링 설정"""
        if self._monitoring is None:
            self._monitoring = MonitoringConfig()
        return self._monitoring

    def is_production(self) -> bool:
        """프로덕션 환경 여부"""
        return self.env == "production"

    def is_development(self) -> bool:
        """개발 환경 여부"""
        return self.env == "development"


@lru_cache()
def get_settings() -> Settings:
    """설정 싱글톤 인스턴스 반환"""
    return Settings()


# 전역 설정 인스턴스
settings = get_settings()
