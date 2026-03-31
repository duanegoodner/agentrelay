"""Tests for FileCredentialProvider implementation."""

from pathlib import Path

import pytest

from agentrelay.sandbox import (
    AnthropicCredential,
    CredentialProvider,
    CredentialType,
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

    def test_missing_tier_raises(self, tmp_path: Path) -> None:
        """Raises ValueError when requested tier is not in the file."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("token_tiers:\n" "  standard:\n" "    GH_TOKEN: ghp_std\n")
        provider = FileCredentialProvider(path=cred_file)
        with pytest.raises(ValueError, match="elevated"):
            provider.resolve(TokenTier.ELEVATED)

    def test_no_token_tiers_section_raises_on_resolve(self, tmp_path: Path) -> None:
        """File without token_tiers section raises on any resolve."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("{}\n")
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
        cred_file.write_text("token_tiers:\n  standard:\n    GH_TOKEN: ghp\n")
        provider = FileCredentialProvider(path=cred_file)
        d1 = provider.resolve(TokenTier.STANDARD)
        d2 = provider.resolve(TokenTier.STANDARD)
        assert d1 == d2
        assert d1 is not d2


class TestFileCredentialProviderMigration:
    """Tests for defaults → anthropic migration guard."""

    def test_defaults_with_anthropic_key_raises_migration_error(
        self, tmp_path: Path
    ) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "defaults:\n"
            "  ANTHROPIC_API_KEY: sk-ant-xxx\n"
            "token_tiers:\n"
            "  standard:\n"
            "    GH_TOKEN: ghp_std\n"
        )
        with pytest.raises(ValueError, match="no longer supported"):
            FileCredentialProvider(path=cred_file)

    def test_defaults_without_anthropic_key_allowed(self, tmp_path: Path) -> None:
        """defaults section without ANTHROPIC_API_KEY is accepted (no migration needed)."""
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "defaults:\n"
            "  SOME_OTHER_KEY: value\n"
            "token_tiers:\n"
            "  standard: {}\n"
        )
        # Should not raise.
        FileCredentialProvider(path=cred_file)


class TestResolveAnthropic:
    """Tests for resolve_anthropic method."""

    def test_no_section_returns_none(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text("token_tiers:\n  standard: {}\n")
        provider = FileCredentialProvider(path=cred_file)
        assert provider.resolve_anthropic() is None

    def test_single_entry_auto_selects(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  my_key:\n"
            "    type: api_key\n"
            "    key: sk-ant-test\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        cred = provider.resolve_anthropic()
        assert cred is not None
        assert cred.name == "my_key"
        assert cred.credential_type == CredentialType.API_KEY
        assert cred.api_key == "sk-ant-test"

    def test_select_by_name(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  dev:\n"
            "    type: api_key\n"
            "    key: sk-dev\n"
            "  max:\n"
            "    type: oauth\n"
            "    path: ~/.claude/.credentials.json\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        cred = provider.resolve_anthropic("max")
        assert cred is not None
        assert cred.name == "max"
        assert cred.credential_type == CredentialType.OAUTH
        assert cred.oauth_path == Path("~/.claude/.credentials.json").expanduser()

    def test_multiple_entries_no_name_raises(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  dev:\n"
            "    type: api_key\n"
            "    key: sk-dev\n"
            "  max:\n"
            "    type: oauth\n"
            "    path: ~/.claude/.credentials.json\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        with pytest.raises(ValueError, match="Multiple Anthropic credentials"):
            provider.resolve_anthropic()

    def test_unknown_name_raises(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  dev:\n"
            "    type: api_key\n"
            "    key: sk-dev\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        with pytest.raises(ValueError, match="not found"):
            provider.resolve_anthropic("nonexistent")

    def test_api_key_type_fields(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  test:\n"
            "    type: api_key\n"
            "    key: sk-ant-xxx\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        cred = provider.resolve_anthropic("test")
        assert isinstance(cred, AnthropicCredential)
        assert cred.credential_type == CredentialType.API_KEY
        assert cred.api_key == "sk-ant-xxx"
        assert cred.oauth_path is None

    def test_oauth_type_fields(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  test:\n"
            "    type: oauth\n"
            "    path: ~/.claude/.credentials.json\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        cred = provider.resolve_anthropic("test")
        assert isinstance(cred, AnthropicCredential)
        assert cred.credential_type == CredentialType.OAUTH
        assert cred.oauth_path == Path("~/.claude/.credentials.json").expanduser()
        assert cred.api_key is None

    def test_anthropic_names_property(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  zebra:\n"
            "    type: api_key\n"
            "    key: sk-z\n"
            "  alpha:\n"
            "    type: api_key\n"
            "    key: sk-a\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        assert provider.anthropic_names == ["alpha", "zebra"]

    def test_missing_type_field_raises(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  bad:\n"
            "    key: sk-xxx\n"
        )
        with pytest.raises(ValueError, match="must have a 'type' field"):
            FileCredentialProvider(path=cred_file)

    def test_api_key_missing_key_and_key_file_raises(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  bad:\n"
            "    type: api_key\n"
        )
        with pytest.raises(ValueError, match="'key' or 'key_file'"):
            FileCredentialProvider(path=cred_file)

    def test_api_key_from_file(self, tmp_path: Path) -> None:
        key_file = tmp_path / "api_key"
        key_file.write_text("sk-ant-from-file")
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  test:\n"
            "    type: api_key\n"
            f"    key_file: {key_file}\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        cred = provider.resolve_anthropic("test")
        assert cred is not None
        assert cred.api_key == "sk-ant-from-file"

    def test_api_key_file_strips_whitespace(self, tmp_path: Path) -> None:
        key_file = tmp_path / "api_key"
        key_file.write_text("  sk-ant-padded  \n")
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  test:\n"
            "    type: api_key\n"
            f"    key_file: {key_file}\n"
        )
        provider = FileCredentialProvider(path=cred_file)
        cred = provider.resolve_anthropic("test")
        assert cred is not None
        assert cred.api_key == "sk-ant-padded"

    def test_api_key_file_not_found_raises(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  bad:\n"
            "    type: api_key\n"
            f"    key_file: {tmp_path / 'nonexistent'}\n"
        )
        with pytest.raises(ValueError, match="key_file not found"):
            FileCredentialProvider(path=cred_file)

    def test_api_key_both_key_and_key_file_raises(self, tmp_path: Path) -> None:
        key_file = tmp_path / "api_key"
        key_file.write_text("sk-ant-file")
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  bad:\n"
            "    type: api_key\n"
            "    key: sk-ant-inline\n"
            f"    key_file: {key_file}\n"
        )
        with pytest.raises(ValueError, match="both 'key' and 'key_file'"):
            FileCredentialProvider(path=cred_file)

    def test_oauth_missing_path_raises(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  bad:\n"
            "    type: oauth\n"
        )
        with pytest.raises(ValueError, match="must have a 'path' field"):
            FileCredentialProvider(path=cred_file)

    def test_invalid_type_value_raises(self, tmp_path: Path) -> None:
        cred_file = tmp_path / "creds.yaml"
        cred_file.write_text(
            "token_tiers:\n  standard: {}\n"
            "anthropic:\n"
            "  bad:\n"
            "    type: invalid\n"
        )
        with pytest.raises(ValueError, match="must be one of"):
            FileCredentialProvider(path=cred_file)
