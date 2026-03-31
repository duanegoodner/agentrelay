"""File-based credential provider — reads credentials from a YAML file.

This module provides :class:`FileCredentialProvider`, which reads credential
mappings from a YAML file organized by token tier and optional Anthropic
credentials.  Each call to :meth:`resolve` returns the requested tier's
environment variables (e.g., ``GH_TOKEN``).  Anthropic credentials are
resolved separately via :meth:`resolve_anthropic`.

Expected YAML schema::

    token_tiers:
      read_only:
        GH_TOKEN: ghp_xxxx
      standard:
        GH_TOKEN: ghp_yyyy
      elevated:
        GH_TOKEN: ghp_zzzz

    anthropic:
      dev_api_key:
        type: api_key
        key: sk-ant-xxxx
      max_plan:
        type: oauth
        path: ~/.claude/.credentials.json

Classes:
    FileCredentialProvider: Resolves credentials from a YAML file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from agentrelay.sandbox.core.config import (
    AnthropicCredential,
    CredentialType,
    TokenTier,
)


class FileCredentialProvider:
    """Resolve credential environment variables from a YAML file.

    The YAML file contains a ``token_tiers`` mapping keyed by tier value
    and an optional ``anthropic`` mapping of named Anthropic credentials.
    On :meth:`resolve`, the requested tier's entries are returned.

    The file is read once at construction time and cached.

    Attributes:
        path: Path to the YAML credential file.
    """

    def __init__(self, path: Path) -> None:
        """Load and parse the credential YAML file.

        Args:
            path: Path to the YAML credential file.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is not valid YAML or has an
                unexpected structure.
        """
        self.path = path
        text = path.read_text()
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError(
                f"Credential file must be a YAML mapping, got {type(data).__name__}"
            )

        # Migration guard: reject old `defaults` section with ANTHROPIC_API_KEY.
        defaults = data.get("defaults", {})
        if isinstance(defaults, dict) and "ANTHROPIC_API_KEY" in defaults:
            raise ValueError(
                "The 'defaults' section with ANTHROPIC_API_KEY is no longer supported. "
                "Move Anthropic credentials to the 'anthropic' section:\n\n"
                "  anthropic:\n"
                "    my_key:\n"
                "      type: api_key\n"
                "      key: <your-api-key>\n"
            )

        raw_tiers = data.get("token_tiers", {})
        if not isinstance(raw_tiers, dict):
            raise ValueError(
                f"token_tiers must be a mapping, got {type(raw_tiers).__name__}"
            )
        self._tiers: dict[str, dict[str, str]] = {}
        for tier_key, tier_vars in raw_tiers.items():
            if not isinstance(tier_vars, dict):
                raise ValueError(
                    f"token_tiers.{tier_key} must be a mapping, "
                    f"got {type(tier_vars).__name__}"
                )
            self._tiers[str(tier_key)] = {str(k): str(v) for k, v in tier_vars.items()}

        # Parse optional anthropic credentials section.
        raw_anthropic = data.get("anthropic", {})
        if not isinstance(raw_anthropic, dict):
            raise ValueError(
                f"anthropic must be a mapping, got {type(raw_anthropic).__name__}"
            )
        self._anthropic: dict[str, AnthropicCredential] = {}
        for name, entry in raw_anthropic.items():
            if not isinstance(entry, dict):
                raise ValueError(
                    f"anthropic.{name} must be a mapping, "
                    f"got {type(entry).__name__}"
                )
            if "type" not in entry:
                raise ValueError(f"anthropic.{name} must have a 'type' field")
            try:
                ctype = CredentialType(entry["type"])
            except ValueError:
                raise ValueError(
                    f"anthropic.{name}.type must be one of "
                    f"{[t.value for t in CredentialType]}, got {entry['type']!r}"
                )
            if ctype == CredentialType.API_KEY:
                if "key" not in entry:
                    raise ValueError(
                        f"anthropic.{name} with type 'api_key' must have a 'key' field"
                    )
                self._anthropic[str(name)] = AnthropicCredential(
                    name=str(name),
                    credential_type=ctype,
                    api_key=str(entry["key"]),
                )
            elif ctype == CredentialType.OAUTH:
                if "path" not in entry:
                    raise ValueError(
                        f"anthropic.{name} with type 'oauth' must have a 'path' field"
                    )
                self._anthropic[str(name)] = AnthropicCredential(
                    name=str(name),
                    credential_type=ctype,
                    oauth_path=Path(str(entry["path"])).expanduser(),
                )

    def resolve(self, tier: TokenTier) -> dict[str, str]:
        """Resolve credentials for the given token tier.

        Returns the tier-specific credential environment variables.

        Args:
            tier: Permission tier to resolve credentials for.

        Returns:
            Dictionary of environment variable names to values.

        Raises:
            ValueError: If the requested tier is not defined in the
                credential file.
        """
        if tier.value not in self._tiers:
            raise ValueError(
                f"Token tier {tier.value!r} not found in credential file "
                f"{self.path}; available tiers: "
                f"{sorted(self._tiers.keys())}"
            )
        return dict(self._tiers[tier.value])

    def resolve_anthropic(
        self, name: Optional[str] = None
    ) -> Optional[AnthropicCredential]:
        """Resolve a named Anthropic credential.

        Args:
            name: Credential name from the YAML ``anthropic`` section.
                When ``None``, auto-selects if exactly one entry exists.

        Returns:
            The resolved credential, or ``None`` if no ``anthropic``
            section is defined.

        Raises:
            ValueError: If ``name`` is not found, or if multiple entries
                exist and ``name`` is not specified.
        """
        if not self._anthropic:
            return None
        if name is not None:
            if name not in self._anthropic:
                raise ValueError(
                    f"Anthropic credential {name!r} not found in {self.path}; "
                    f"available: {sorted(self._anthropic.keys())}"
                )
            return self._anthropic[name]
        if len(self._anthropic) == 1:
            return next(iter(self._anthropic.values()))
        raise ValueError(
            f"Multiple Anthropic credentials defined in {self.path}; "
            f"specify one with --anthropic-credential: "
            f"{sorted(self._anthropic.keys())}"
        )

    @property
    def anthropic_names(self) -> list[str]:
        """Sorted list of available Anthropic credential names."""
        return sorted(self._anthropic.keys())
