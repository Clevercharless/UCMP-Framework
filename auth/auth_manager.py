"""
auth.auth_manager
==================
`AuthenticationManager` is the third pipeline stage. It runs immediately
after ConfigurationManager and SIMULATES authenticating to both the Azure
Databricks source workspace and the AWS Databricks target workspace,
using only the config values ConfigurationManager already resolved.

No real credentials are read, requested, or transmitted. This module
exists to model where auth would plug into a real migration pipeline
(and to give the Deployment Engine, later, a token to "present" during its
own simulated push) without requiring any paid cloud account to run the
demo end to end.
"""

from __future__ import annotations

from typing import Any, Dict

from auth.providers import AWSAuthProvider, AzureAuthProvider
from auth.token_store import TokenStore
from common.exceptions import AuthenticationError
from common.logging_config import get_logger
from orchestrator.context import PipelineContext
from orchestrator.interfaces import PipelineStage

logger = get_logger(__name__)

DEFAULT_AZURE_PRINCIPAL = "svc-ucmp-azure-migration"
DEFAULT_AWS_PRINCIPAL = "svc-ucmp-aws-migration"
DEFAULT_AZURE_SCOPES = ["workspace.read", "secrets.read", "repos.read"]
DEFAULT_AWS_SCOPES = ["workspace.write", "catalog.write", "repos.write"]


class AuthenticationManager(PipelineStage):
    """
    Simulated authentication stage. Reads `context.config["source"]` and
    `context.config["target"]` (populated by ConfigurationManager),
    authenticates against both simulated providers, and stores the
    resulting tokens in a `TokenStore` kept on the manager instance.

    Downstream stages that need to "present" a token (e.g. a future
    Deployment Engine) can be given this manager's `token_store` rather
    than re-deriving credentials themselves.
    """

    name = "AuthenticationManager"

    def __init__(self, token_ttl_seconds: int = 3600):
        self._token_ttl_seconds = token_ttl_seconds
        self.token_store = TokenStore()

    def run(self, context: PipelineContext) -> PipelineContext:
        if not context.config:
            raise AuthenticationError(
                "AuthenticationManager requires context.config to be populated "
                "(run ConfigurationManager first)"
            )

        source_cfg = context.config.get("source", {})
        target_cfg = context.config.get("target", {})

        azure_token = self._authenticate_azure(source_cfg)
        self.token_store.put(azure_token)

        aws_token = self._authenticate_aws(target_cfg)
        self.token_store.put(aws_token)

        context.set_artifact(
            "auth_session",
            {
                "azure_databricks": azure_token.to_summary_dict(),
                "aws_databricks": aws_token.to_summary_dict(),
            },
        )
        context.metadata["authenticated"] = True

        logger.info(
            "Authentication simulation complete: azure=%s aws=%s",
            azure_token.masked(),
            aws_token.masked(),
        )
        return context

    # -- internals --------------------------------------------------------

    def _authenticate_azure(self, source_cfg: Dict[str, Any]):
        provider = AzureAuthProvider(
            workspace_url=source_cfg.get("workspace_url", ""),
            key_vault_name=source_cfg.get("key_vault_name", ""),
        )
        return provider.authenticate(
            principal=DEFAULT_AZURE_PRINCIPAL,
            scopes=DEFAULT_AZURE_SCOPES,
            ttl_seconds=self._token_ttl_seconds,
        )

    def _authenticate_aws(self, target_cfg: Dict[str, Any]):
        provider = AWSAuthProvider(
            workspace_url=target_cfg.get("workspace_url", ""),
            catalog_name=target_cfg.get("catalog_name", ""),
        )
        return provider.authenticate(
            principal=DEFAULT_AWS_PRINCIPAL,
            scopes=DEFAULT_AWS_SCOPES,
            ttl_seconds=self._token_ttl_seconds,
        )
