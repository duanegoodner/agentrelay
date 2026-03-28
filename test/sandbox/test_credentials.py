"""Tests for CredentialProvider protocol and NullCredentialProvider."""

from agentrelay.sandbox import (
    CredentialProvider,
    NullCredentialProvider,
    TokenTier,
)


class TestCredentialProviderProtocol:
    """Tests for the CredentialProvider protocol."""

    def test_is_runtime_checkable(self) -> None:
        """NullCredentialProvider satisfies the protocol via isinstance."""
        assert isinstance(NullCredentialProvider(), CredentialProvider)


class TestNullCredentialProvider:
    """Tests for NullCredentialProvider implementation."""

    def test_satisfies_protocol(self) -> None:
        """NullCredentialProvider satisfies the CredentialProvider protocol."""
        provider = NullCredentialProvider()
        assert isinstance(provider, CredentialProvider)

    def test_resolve_read_only_returns_empty(self) -> None:
        """Returns empty dict for READ_ONLY tier."""
        provider = NullCredentialProvider()
        assert provider.resolve(TokenTier.READ_ONLY) == {}

    def test_resolve_standard_returns_empty(self) -> None:
        """Returns empty dict for STANDARD tier."""
        provider = NullCredentialProvider()
        assert provider.resolve(TokenTier.STANDARD) == {}

    def test_resolve_elevated_returns_empty(self) -> None:
        """Returns empty dict for ELEVATED tier."""
        provider = NullCredentialProvider()
        assert provider.resolve(TokenTier.ELEVATED) == {}
