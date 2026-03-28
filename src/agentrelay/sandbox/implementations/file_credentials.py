"""File-based credential provider — reads credentials from a YAML file.

This module provides :class:`FileCredentialProvider`, which reads credential
mappings from a YAML file organized by token tier. Each call to
:meth:`resolve` merges tier-agnostic defaults with the requested tier's
specific credentials (tier-specific values override defaults on collision).

Expected YAML schema::

    token_tiers:
      read_only:
        GH_TOKEN: ghp_xxxx
      standard:
        GH_TOKEN: ghp_yyyy
      elevated:
        GH_TOKEN: ghp_zzzz
    defaults:
      ANTHROPIC_API_KEY: sk-ant-xxxx

Classes:
    FileCredentialProvider: Resolves credentials from a YAML file.
"""

from pathlib import Path

import yaml

from agentrelay.sandbox.core.config import TokenTier


class FileCredentialProvider:
    """Resolve credential environment variables from a YAML file.

    The YAML file contains an optional ``defaults`` mapping (injected for
    every tier) and a ``token_tiers`` mapping keyed by tier value. On
    :meth:`resolve`, the defaults are merged with the requested tier's
    entries; tier-specific values override defaults on key collision.

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
        self._defaults: dict[str, str] = {
            str(k): str(v) for k, v in data.get("defaults", {}).items()
        }
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

    def resolve(self, tier: TokenTier) -> dict[str, str]:
        """Resolve credentials for the given token tier.

        Returns defaults merged with the tier-specific credentials.
        Tier-specific values override defaults on key collision.

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
        result = dict(self._defaults)
        result.update(self._tiers[tier.value])
        return result
