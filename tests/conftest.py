import pytest


@pytest.fixture(autouse=True)
def _disable_local_env_file(monkeypatch):
    monkeypatch.setenv("HERMES_ENV_FILE", "/tmp/hermes-merry-test-env-does-not-exist")
