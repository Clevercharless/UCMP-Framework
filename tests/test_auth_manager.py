"""
tests.test_auth_manager
========================
Unit tests for auth.credentials, auth.providers, auth.token_store, and
auth.auth_manager.AuthenticationManager.
"""

from __future__ import annotations

import time

import pytest

from auth.auth_manager import AuthenticationManager
from auth.credentials import SimulatedToken
from auth.providers import AWSAuthProvider, AzureAuthProvider
from auth.token_store import TokenStore
from common.exceptions import AuthenticationError
from config.config_manager import ConfigurationManager
from orchestrator.context import PipelineContext
from orchestrator.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# SimulatedToken
# ---------------------------------------------------------------------------

def test_token_not_expired_when_fresh():
    now = time.time()
    token = SimulatedToken(
        principal="svc-test", platform="azure_databricks", token_value="SIM.abcdef123456",
        issued_at=now, expires_at=now + 3600, scopes=["workspace.read"],
    )
    assert token.is_expired is False
    assert token.ttl_seconds_remaining > 0


def test_token_expired_when_ttl_elapsed():
    now = time.time()
    token = SimulatedToken(
        principal="svc-test", platform="azure_databricks", token_value="SIM.abcdef123456",
        issued_at=now - 100, expires_at=now - 1, scopes=[],
    )
    assert token.is_expired is True
    assert token.ttl_seconds_remaining == 0.0


def test_token_masking_hides_all_but_last_4_chars():
    token = SimulatedToken(
        principal="svc-test", platform="azure_databricks", token_value="SIM-AZURE-AAD.0123456789abcdef",
        issued_at=time.time(), expires_at=time.time() + 3600, scopes=[],
    )
    masked = token.masked()
    assert masked.endswith("cdef")
    assert "0123456789ab" not in masked


def test_token_summary_dict_never_contains_raw_token():
    token = SimulatedToken(
        principal="svc-test", platform="aws_databricks", token_value="SIM-AWS-STS.secretlookingvalue",
        issued_at=time.time(), expires_at=time.time() + 3600, scopes=["catalog.write"],
    )
    summary = token.to_summary_dict()
    assert "secretlookingvalue" not in str(summary)
    assert summary["token_masked"] != token.token_value


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

def test_azure_provider_requires_workspace_url():
    with pytest.raises(AuthenticationError, match="workspace_url"):
        AzureAuthProvider(workspace_url="", key_vault_name="kv")


def test_azure_provider_requires_key_vault():
    with pytest.raises(AuthenticationError, match="key_vault_name"):
        AzureAuthProvider(workspace_url="https://adb.example.net", key_vault_name="")


def test_azure_provider_mints_token_with_expected_prefix():
    provider = AzureAuthProvider(workspace_url="https://adb.example.net", key_vault_name="kv")
    token = provider.authenticate(principal="svc-azure", scopes=["workspace.read"])
    assert token.token_value.startswith("SIM-AZURE-AAD.")
    assert token.platform == "azure_databricks"
    assert token.principal == "svc-azure"


def test_aws_provider_requires_workspace_url():
    with pytest.raises(AuthenticationError, match="workspace_url"):
        AWSAuthProvider(workspace_url="", catalog_name="catalog")


def test_aws_provider_requires_catalog_name():
    with pytest.raises(AuthenticationError, match="catalog_name"):
        AWSAuthProvider(workspace_url="https://dbc.example.com", catalog_name="")


def test_aws_provider_mints_token_with_expected_prefix():
    provider = AWSAuthProvider(workspace_url="https://dbc.example.com", catalog_name="catalog")
    token = provider.authenticate(principal="svc-aws", scopes=["catalog.write"])
    assert token.token_value.startswith("SIM-AWS-STS.")
    assert token.platform == "aws_databricks"


def test_tokens_from_same_provider_are_unique():
    provider = AzureAuthProvider(workspace_url="https://adb.example.net", key_vault_name="kv")
    t1 = provider.authenticate(principal="svc-azure", scopes=[])
    t2 = provider.authenticate(principal="svc-azure", scopes=[])
    assert t1.token_value != t2.token_value


# ---------------------------------------------------------------------------
# TokenStore
# ---------------------------------------------------------------------------

def test_token_store_put_and_get():
    store = TokenStore()
    token = SimulatedToken(
        principal="p", platform="azure_databricks", token_value="SIM.x",
        issued_at=time.time(), expires_at=time.time() + 100, scopes=[],
    )
    store.put(token)
    assert store.get("azure_databricks") is token
    assert store.is_valid("azure_databricks") is True


def test_token_store_require_valid_raises_when_missing():
    store = TokenStore()
    with pytest.raises(AuthenticationError, match="No simulated token"):
        store.require_valid("azure_databricks")


def test_token_store_require_valid_raises_when_expired():
    store = TokenStore()
    expired = SimulatedToken(
        principal="p", platform="aws_databricks", token_value="SIM.x",
        issued_at=time.time() - 200, expires_at=time.time() - 1, scopes=[],
    )
    store.put(expired)
    with pytest.raises(AuthenticationError, match="expired"):
        store.require_valid("aws_databricks")


def test_token_store_purge_expired():
    store = TokenStore()
    fresh = SimulatedToken(
        principal="p", platform="azure_databricks", token_value="SIM.x",
        issued_at=time.time(), expires_at=time.time() + 3600, scopes=[],
    )
    expired = SimulatedToken(
        principal="p", platform="aws_databricks", token_value="SIM.y",
        issued_at=time.time() - 200, expires_at=time.time() - 1, scopes=[],
    )
    store.put(fresh)
    store.put(expired)

    purged_count = store.purge_expired()

    assert purged_count == 1
    assert store.get("azure_databricks") is not None
    assert store.get("aws_databricks") is None


# ---------------------------------------------------------------------------
# AuthenticationManager (PipelineStage)
# ---------------------------------------------------------------------------

def test_auth_manager_requires_config_populated_first():
    manager = AuthenticationManager()
    context = PipelineContext()  # config never populated
    with pytest.raises(AuthenticationError, match="ConfigurationManager"):
        manager.run(context)


def test_auth_manager_populates_auth_session_artifact():
    config_manager = ConfigurationManager(config_path=None, env={})
    auth_manager = AuthenticationManager()

    context = PipelineContext()
    context = config_manager.run(context)
    context = auth_manager.run(context)

    session = context.get_artifact("auth_session")
    assert session is not None
    assert session["azure_databricks"]["platform"] == "azure_databricks"
    assert session["aws_databricks"]["platform"] == "aws_databricks"
    assert context.metadata["authenticated"] is True


def test_auth_manager_never_exposes_raw_token_in_artifacts():
    config_manager = ConfigurationManager(config_path=None, env={})
    auth_manager = AuthenticationManager()

    context = config_manager.run(PipelineContext())
    context = auth_manager.run(context)

    session = context.get_artifact("auth_session")
    azure_token_raw = auth_manager.token_store.get("azure_databricks").token_value
    assert azure_token_raw not in str(session)


def test_auth_manager_runs_as_stage_after_configuration_manager():
    orchestrator = Orchestrator(
        stages=[ConfigurationManager(config_path=None, env={}), AuthenticationManager()]
    )
    context = orchestrator.run()

    assert context.summary()["overall_status"] == "SUCCESS"
    assert context.metadata["authenticated"] is True


def test_auth_manager_token_store_has_both_platform_tokens():
    config_manager = ConfigurationManager(config_path=None, env={})
    auth_manager = AuthenticationManager()

    context = config_manager.run(PipelineContext())
    auth_manager.run(context)

    assert auth_manager.token_store.is_valid("azure_databricks")
    assert auth_manager.token_store.is_valid("aws_databricks")
