"""設定中心 (src/config.py) 測試 —— Phase 1 設定收斂。

契約：預設值與遷移前的硬編碼一致（不改行為）；所有值可由環境變數覆寫。
"""
import importlib

import pytest


def _reload_config(monkeypatch, **env):
    """以指定環境變數重載 config 模組，回傳新模組物件。"""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import src.config as config
    return importlib.reload(config)


@pytest.mark.unit
def test_defaults_match_pre_migration_hardcodes(monkeypatch):
    for var in ("MONGODB_URI", "MONGODB_DATABASE", "OLLAMA_URL",
                "OLLAMA_CONSENSUS_URL", "TWSTOCK_PROJECT_ROOT"):
        monkeypatch.delenv(var, raising=False)
    cfg = _reload_config(monkeypatch)
    assert cfg.MONGODB_URI == "mongodb://localhost:27017"
    assert cfg.MONGODB_DATABASE == "tw_stock_analysis"
    assert cfg.OLLAMA_URL == "http://172.16.9.28:11434"
    assert cfg.OLLAMA_CONSENSUS_URL == "http://172.16.9.27:11434"


@pytest.mark.unit
def test_env_override_is_respected(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        MONGODB_URI="mongodb://db:27017",
        MONGODB_DATABASE="test_db",
        OLLAMA_URL="http://gpu-a:11434",
        OLLAMA_CONSENSUS_URL="http://gpu-b:11434",
    )
    assert cfg.MONGODB_URI == "mongodb://db:27017"
    assert cfg.MONGODB_DATABASE == "test_db"
    assert cfg.OLLAMA_URL == "http://gpu-a:11434"
    assert cfg.OLLAMA_CONSENSUS_URL == "http://gpu-b:11434"


@pytest.mark.unit
def test_project_root_is_portable_not_hardcoded(monkeypatch):
    """PROJECT_ROOT 由檔案位置推導，不得含硬編碼 /home/mdsadmin。"""
    monkeypatch.delenv("TWSTOCK_PROJECT_ROOT", raising=False)
    cfg = _reload_config(monkeypatch)
    assert "mdsadmin" not in str(cfg.PROJECT_ROOT)
    # results 目錄應在專案根下
    assert str(cfg.RESULTS_DIR).startswith(str(cfg.PROJECT_ROOT))


@pytest.mark.unit
def test_project_root_env_override(monkeypatch):
    cfg = _reload_config(monkeypatch, TWSTOCK_PROJECT_ROOT="/opt/app")
    assert str(cfg.PROJECT_ROOT).replace("\\", "/") == "/opt/app"


@pytest.mark.unit
def test_mongo_client_helper_uses_config(monkeypatch):
    """get_db() 應以 config 的 URI/DB 建立連線（以 mock 驗證，不真連）。"""
    cfg = _reload_config(monkeypatch, MONGODB_URI="mongodb://x:27017",
                         MONGODB_DATABASE="d")
    calls = {}

    class _FakeClient:
        def __init__(self, uri, **kw):
            calls["uri"] = uri

        def __getitem__(self, name):
            calls["db"] = name
            return f"DB:{name}"

    monkeypatch.setattr(cfg, "MongoClient", _FakeClient)
    db = cfg.get_db()
    assert calls["uri"] == "mongodb://x:27017"
    assert calls["db"] == "d"
    assert db == "DB:d"
