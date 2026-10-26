"""
auth.token_store
=================
In-memory store for `SimulatedToken` objects, keyed by platform. Purely a
process-local cache — nothing here is persisted to disk or sent over the
network. Exists so a single migration run has one obvious place to ask
"am I currently authenticated to platform X, and is that token still
valid?" without every stage re-deriving that logic.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from auth.credentials import SimulatedToken
from common.exceptions import AuthenticationError
from common.logging_config import get_logger

logger = get_logger(__name__)


class TokenStore:
    """Simple in-memory {platform: SimulatedToken} cache with expiry checks."""

    def __init__(self):
        self._tokens: Dict[str, SimulatedToken] = {}

    def put(self, token: SimulatedToken) -> None:
        self._tokens[token.platform] = token

    def get(self, platform: str) -> Optional[SimulatedToken]:
        return self._tokens.get(platform)

    def require_valid(self, platform: str) -> SimulatedToken:
        """
        Return the current token for `platform`, raising AuthenticationError
        if there isn't one or it has expired. Downstream stages (e.g. the
        future Repository Manager / Deployment Engine) can call this rather
        than duplicating None/expiry checks.
        """
        token = self._tokens.get(platform)
        if token is None:
            raise AuthenticationError(f"No simulated token found for platform '{platform}'")
        if token.is_expired:
            raise AuthenticationError(
                f"Simulated token for platform '{platform}' expired at {token.expires_at}"
            )
        return token

    def is_valid(self, platform: str) -> bool:
        token = self._tokens.get(platform)
        return token is not None and not token.is_expired

    def all_tokens(self) -> List[SimulatedToken]:
        return list(self._tokens.values())

    def purge_expired(self) -> int:
        """Remove expired tokens; returns the number purged."""
        expired = [p for p, t in self._tokens.items() if t.is_expired]
        for platform in expired:
            del self._tokens[platform]
        if expired:
            logger.info("Purged %d expired token(s): %s", len(expired), expired)
        return len(expired)
