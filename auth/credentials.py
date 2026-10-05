"""
auth.credentials
=================
Data model for SIMULATED authentication tokens.

Nothing in this file ever performs network I/O, contacts Azure AD, AWS STS,
or any real identity provider. Tokens are locally generated, opaque
strings that only need to *look* plausible for demo/reporting purposes —
there is no cryptographic validity and they are never sent anywhere.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class SimulatedToken:
    """
    A locally-generated stand-in for a real bearer/session token.

    Attributes:
        principal: The simulated service principal / IAM role name that
            "authenticated" (e.g. "svc-ucmp-azure-migration").
        platform: Which platform this token is for — "azure_databricks" or
            "aws_databricks".
        token_value: The opaque simulated token string. Never a real
            credential; safe to print in full only in local demo logs,
            but the AuthenticationManager masks it by default anyway.
        issued_at: Unix timestamp when the token was minted.
        expires_at: Unix timestamp after which `is_expired` becomes True.
        scopes: List of simulated permission scopes granted, e.g.
            ["workspace.read", "secrets.read"].
    """

    principal: str
    platform: str
    token_value: str
    issued_at: float
    expires_at: float
    scopes: List[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    @property
    def ttl_seconds_remaining(self) -> float:
        return max(0.0, self.expires_at - time.time())

    def masked(self) -> str:
        """Return the token value with all but the last 4 characters hidden."""
        if len(self.token_value) <= 4:
            return "*" * len(self.token_value)
        return f"{'*' * (len(self.token_value) - 4)}{self.token_value[-4:]}"

    def to_summary_dict(self) -> dict:
        """Safe-to-log/report summary — never includes the raw token value."""
        return {
            "principal": self.principal,
            "platform": self.platform,
            "token_masked": self.masked(),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "scopes": list(self.scopes),
            "is_expired": self.is_expired,
        }
