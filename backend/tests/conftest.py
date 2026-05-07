import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("APS_CLIENT_ID", "test_id")
    monkeypatch.setenv("APS_CLIENT_SECRET", "test_secret")
    monkeypatch.setenv("APS_BUCKET", "test-bucket")
    monkeypatch.setenv("APS_APPBUNDLE_ALIAS", "prod")
    monkeypatch.setenv("APS_ACTIVITY_ALIAS", "prod")
