"""Tests for FileCredentialProvider implementation."""

from pathlib import Path

import pytest

from agentrelay.sandbox import (
    CredentialProvider,
    FileCredentialProvider,
    TokenTier,
)


class TestFileCredentialProvider:
    """Tests for FileCredentialProvider."""

    def test_satisfies_protocol(self, tmp_path: Path) -> None:
        """FileCredentialProvider satisfies the CredentialProvider protocol."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("token_tiers:\n  standard: {}\n")
        provider = FileCredentialProvider(path=cred_file)
        assert isinstance(provider, CredentialProvider)

    def test_resolve_returns_tier_specific_vars(self, tmp_path: Path) -> None:
        """Returns env vars for the requested tier."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n"
            "  read_only:\n"
            "    GH_TOKEN: ghp_ro\n"
            "  standard:\n"
            "    GH_TOKEN: ghp_std\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        assert provider.resolve(TokenTier.READ_ONLY) == {"GH_TOKEN": "ghp_ro"}
        assert provider.resolve(TokenTier.STANDARD) == {"GH_TOKEN": "ghp_std"}

    def test_resolve_merges_defaults(self, tmp_path: Path) -> None:
        """Defaults are merged with tier-specific vars."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "defaults:\n"
            "  ANTHROPIC_API_KEY: sk-ant-xxx\n"
            "token_tiers:\n"
            "  standard:\n"
            "    GH_TOKEN: ghp_std\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        result = provider.resolve(TokenTier.STANDARD)
        assert result == {
            "ANTHROPIC_API_KEY": "sk-ant-xxx",
            "GH_TOKEN": "ghp_std",
        }

    def test_tier_overrides_defaults_on_collision(self, tmp_path: Path) -> None:
        """Tier-specific value wins when key exists in both defaults and tier."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "defaults:\n"
            "  GH_TOKEN: ghp_default\n"
            "token_tiers:\n"
            "  elevated:\n"
            "    GH_TOKEN: ghp_elevated\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        result = provider.resolve(TokenTier.ELEVATED)
        assert result == {"GH_TOKEN": "ghp_elevated"}

    def test_missing_tier_raises(self, tmp_path: Path) -> None:
        """Raises ValueError when requested tier is not in the file."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("token_tiers:\n" "  standard:\n" "    GH_TOKEN: ghp_std\n")
        provider = FileCredentialProvider(path=cred_file)
        with pytest.raises(ValueError, match="elevated"):
            provider.resolve(TokenTier.ELEVATED)

    def test_no_defaults_section(self, tmp_path: Path) -> None:
        """File without defaults section returns only tier-specific vars."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("token_tiers:\n" "  read_only:\n" "    GH_TOKEN: ghp_ro\n")
        provider = FileCredentialProvider(path=cred_file)
        assert provider.resolve(TokenTier.READ_ONLY) == {"GH_TOKEN": "ghp_ro"}

    def test_no_token_tiers_section_raises_on_resolve(self, tmp_path: Path) -> None:
        """File without token_tiers section raises on any resolve."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("defaults:\n  KEY: val\n")
        provider = FileCredentialProvider(path=cred_file)
        with pytest.raises(ValueError, match="standard"):
            provider.resolve(TokenTier.STANDARD)

    def test_empty_mapping_raises_on_resolve(self, tmp_path: Path) -> None:
        """Empty YAML mapping raises on any resolve (no tiers defined)."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("{}\n")
        provider = FileCredentialProvider(path=cred_file)
        with pytest.raises(ValueError, match="standard"):
            provider.resolve(TokenTier.STANDARD)

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when file does not exist."""
        missing = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError):
            FileCredentialProvider(path=missing)

    def test_invalid_yaml_not_mapping_raises(self, tmp_path: Path) -> None:
        """Raises ValueError when file is not a YAML mapping."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("- a list\n- not a mapping\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            FileCredentialProvider(path=cred_file)

    def test_invalid_token_tiers_type_raises(self, tmp_path: Path) -> None:
        """Raises ValueError when token_tiers is not a mapping."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("token_tiers: not_a_mapping\n")
        with pytest.raises(ValueError, match="token_tiers must be a mapping"):
            FileCredentialProvider(path=cred_file)

    def test_invalid_tier_value_type_raises(self, tmp_path: Path) -> None:
        """Raises ValueError when a tier's value is not a mapping."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("token_tiers:\n  standard: not_a_mapping\n")
        with pytest.raises(ValueError, match="token_tiers.standard must be a mapping"):
            FileCredentialProvider(path=cred_file)

    def test_stores_path_attribute(self, tmp_path: Path) -> None:
        """The path attribute is accessible after construction."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("token_tiers:\n  standard: {}\n")
        provider = FileCredentialProvider(path=cred_file)
        assert provider.path == cred_file

    def test_resolve_returns_new_dict_each_call(self, tmp_path: Path) -> None:
        """Each call returns a new dict (mutation-safe)."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "defaults:\n  KEY: val\n" "token_tiers:\n  standard:\n    GH_TOKEN: ghp\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        d1 = provider.resolve(TokenTier.STANDARD)
        d2 = provider.resolve(TokenTier.STANDARD)
        assert d1 == d2
        assert d1 is not d2
