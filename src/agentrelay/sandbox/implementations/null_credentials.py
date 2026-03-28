"""Null credential provider — returns empty credentials for any tier.

This module provides :class:`NullCredentialProvider`, the default credential
provider that returns no credentials. It satisfies the :class:`CredentialProvider`
protocol with a no-op operation, preserving current behavior where no
credential injection occurs.

Classes:
    NullCredentialProvider: Returns empty credentials for any tier.
"""

from agentrelay.sandbox.core.config import TokenTier


class NullCredentialProvider:
    """Credential provider that returns empty credentials for any tier.

    Always returns an empty dictionary regardless of the requested token
    tier. This is the default credential provider for ``SandboxType.NONE``.
    """

    def resolve(self, tier: TokenTier) -> dict[str, str]:
        """Return an empty credential dictionary.

        Args:
            tier: Permission tier (unused).

        Returns:
            An empty dictionary.
        """
        return {}
