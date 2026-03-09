"""
Tests for API database environment configuration.

Red/Green TDD:
1. RED: Add tests for explicit staging/prod env behavior
2. GREEN: Implement URL resolution in agent.api.main
"""

from agent.api import main as api_main


class TestDatabaseEnvConfig:
    """Validate DB URL selection logic for staging vs production."""

    def test_database_url_env_var_takes_precedence(self):
        env = {
            "DATABASE_URL": "sqlite:///./custom.db",
            "APP_ENV": "staging",
        }
        assert api_main.resolve_database_url(env) == "sqlite:///./custom.db"

    def test_app_env_staging_uses_staging_db(self):
        env = {"APP_ENV": "staging"}
        assert api_main.resolve_database_url(env) == "sqlite:///./kanban.staging.db"

    def test_app_env_production_uses_prod_db(self):
        env = {"APP_ENV": "production"}
        assert api_main.resolve_database_url(env) == "sqlite:///./kanban.db"

    def test_default_without_env_is_production_db(self):
        env = {}
        assert api_main.resolve_database_url(env) == "sqlite:///./kanban.db"

    def test_unknown_app_env_falls_back_to_production_db(self):
        env = {"APP_ENV": "qa"}
        assert api_main.resolve_database_url(env) == "sqlite:///./kanban.db"
