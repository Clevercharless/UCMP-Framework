"""
auth.providers
===============
Simulated authentication providers.

`AzureAuthProvider` stands in for Azure AD service-principal auth against
an Azure Databricks workspace + Key Vault. `AWSAuthProvider` stands in for
AWS STS assume-role auth against an AWS Databricks workspace + Unity
Catalog. Both are 100% local: they validate that the config fields they'd
need in real life are present, then mint a `SimulatedToken` with a
platform-appropriate opaque format. Neither ever opens a socket.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from abc import ABC, abstractmethod
from typing import List

from auth.credentials import SimulatedToken
from common.exceptions import AuthenticationError
from common.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_TOKEN_TTL_SECONDS = 3600


class AuthProvider(ABC):
    """Common interface for a (simulated) platform authentication provider."""

    platform_name: str = "unknown"

    @abstractmethod
    def authenticate(
        self,
        principal: str,
        scopes: List[str],
        ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    ) -> SimulatedToken:
        raise NotImplementedError

    def _mint_token(
        self, principal: str, scopes: List[str], ttl_seconds: int, seed: str
    ) -> SimulatedToken:
        """Shared token-minting helper — deterministic-looking, locally generated."""
        now = time.time()
        digest = hashlib.sha256(f"{seed}:{uuid.uuid4()}".encode()).hexdigest()[:32]
        return SimulatedToken(
            principal=principal,
            platform=self.platform_name,
            token_value=f"{self._token_prefix()}.{digest}",
            issued_at=now,
            expires_at=now + ttl_seconds,
            scopes=scopes,
        )

    def _token_prefix(self) -> str:  # pragma: no cover - trivial
        return "SIM"


class AzureAuthProvider(AuthProvider):
    """
    Simulates Azure AD service-principal authentication to an Azure
    Databricks workspace, backed by an Azure Key Vault for secrets.
    """

    platform_name = "azure_databricks"

    def __init__(self, workspace_url: str, key_vault_name: str):
        if not workspace_url:
            raise AuthenticationError(
                "AzureAuthProvider requires source.workspace_url to be set in config"
            )
        if not key_vault_name:
            raise AuthenticationError(
                "AzureAuthProvider requires source.key_vault_name to be set in config"
            )
        self._workspace_url = workspace_url
        self._key_vault_name = key_vault_name

    def authenticate(
        self,
        principal: str,
        scopes: List[str],
        ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    ) -> SimulatedToken:
        logger.info(
            "Simulating Azure AD auth for principal='%s' workspace='%s' key_vault='%s'",
            principal,
            self._workspace_url,
            self._key_vault_name,
        )
        token = self._mint_token(
            principal, scopes, ttl_seconds, seed=f"azure:{self._workspace_url}"
        )
        logger.info("Azure Databricks token minted (masked): %s", token.masked())
        return token

    def _token_prefix(self) -> str:
        return "SIM-AZURE-AAD"


class AWSAuthProvider(AuthProvider):
    """
    Simulates AWS STS assume-role authentication to an AWS Databricks
    workspace, backed by a Unity Catalog metastore.
    """

    platform_name = "aws_databricks"

    def __init__(self, workspace_url: str, catalog_name: str):
        if not workspace_url:
            raise AuthenticationError(
                "AWSAuthProvider requires target.workspace_url to be set in config"
            )
        if not catalog_name:
            raise AuthenticationError(
                "AWSAuthProvider requires target.catalog_name to be set in config"
            )
        self._workspace_url = workspace_url
        self._catalog_name = catalog_name

    def authenticate(
        self,
        principal: str,
        scopes: List[str],
        ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    ) -> SimulatedToken:
        logger.info(
            "Simulating AWS STS assume-role for principal='%s' workspace='%s' catalog='%s'",
            principal,
            self._workspace_url,
            self._catalog_name,
        )
        token = self._mint_token(
            principal, scopes, ttl_seconds, seed=f"aws:{self._workspace_url}"
        )
        logger.info("AWS Databricks token minted (masked): %s", token.masked())
        return token

    def _token_prefix(self) -> str:
        return "SIM-AWS-STS"
