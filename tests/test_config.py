"""
설정 모듈 테스트
"""

import os

import pytest

from dropshipping.config import Settings, get_settings


class TestSettings:
    """Settings 클래스 테스트"""

    def test_default_settings(self, test_env):
        """기본 설정 테스트"""
        settings = Settings()

        assert settings.env == "test"
        assert settings.debug is True
        assert settings.dry_run is True
        assert settings.log_level == "DEBUG"

    def test_path_creation(self, tmp_path):
        """경로 자동 생성 테스트"""
        data_path = tmp_path / "test_data"
        upload_path = tmp_path / "test_uploads"

        settings = Settings(local_data_path=data_path, local_upload_path=upload_path)

        assert data_path.exists()
        assert upload_path.exists()

    def test_environment_checks(self):
        """환경 체크 메서드 테스트"""
        dev_settings = Settings(env="development")
        prod_settings = Settings(env="production")

        assert dev_settings.is_development() is True
        assert dev_settings.is_production() is False

        assert prod_settings.is_development() is False
        assert prod_settings.is_production() is True

    def test_settings_singleton(self, mock_settings):
        """설정 싱글톤 테스트"""
        settings1 = get_settings()
        settings2 = get_settings()

        # 동일한 인스턴스여야 함
        assert settings1 is settings2

    @pytest.mark.parametrize(
        "env_var,expected",
        [
            ("DEBUG", "true"),
            ("DRY_RUN", "true"),
            ("ENV", "test"),
        ],
    )
    def test_env_variables(self, test_env, env_var, expected):
        """환경 변수 로드 테스트"""
        assert os.environ.get(env_var) == expected


class TestSubConfigs:
    """하위 설정 클래스 테스트"""

    def test_optional_configs(self, mock_settings):
        """선택적 설정 테스트"""
        # 테스트 환경에서는 mock_settings를 사용하므로 API 설정이 없음
        # 실제 환경에서는 .env 파일의 값에 따라 결정됨

        # AI와 모니터링은 기본값 사용
        assert mock_settings.ai is not None
        assert mock_settings.monitoring is not None

    def test_ai_config_defaults(self, mock_settings):
        """AI 설정 기본값 테스트"""
        ai_config = mock_settings.ai

        assert ai_config.ollama_host == "http://localhost:11434"
        # 실제 .env 파일에는 더미 값이 있을 수 있음
