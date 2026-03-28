"""Credential provider protocol for resolving token tiers to environment variables.

This module defines the :class:`CredentialProvider` protocol that all credential
provider implementations must satisfy. The protocol is runtime-checkable, so
``isinstance(obj, CredentialProvider)`` works at runtime.

Protocols:
    CredentialProvider: Resolves a token tier into credential environment variables.
"""

from typing import Protocol, runtime_checkable

from agentrelay.sandbox.core.config import TokenTier


@runtime_checkable
class CredentialProvider(Protocol):
    """Protocol for resolving a token tier into credential environment variables.

    Implementations map a :class:`TokenTier` to a dictionary of environment
    variable names and values that should be injected into the agent's
    execution environment.

    Methods:
        resolve: Resolve a token tier into credential environment variables.
    """

    def resolve(self, tier: TokenTier) -> dict[str, str]:
        """Resolve a token tier into credential environment variables.

        Args:
            tier: Permission tier to resolve credentials for.

        Returns:
            Dictionary of environment variable names to values.
        """
        ...
