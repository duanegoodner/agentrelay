"""GitHub-based implementation of :class:`TaskPrProber`.

Classes:
    GhTaskPrProber: Probe task PR merge state via the GitHub CLI.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from agentrelay.ops import gh


@dataclass
class GhTaskPrProber:
    """Probe task PR merge state via the GitHub CLI.

    Stateless thin wrapper over :func:`agentrelay.ops.gh.pr_is_merged` and
    :func:`agentrelay.ops.gh.pr_merge`.  Used by the resumption probe to
    normalize stale ``PR_CREATED`` tasks without depending directly on the
    ``ops/gh`` module, matching the protocol-isolation pattern used by
    :class:`GhTaskMerger`, :class:`GhIntegrationMergeChecker`, and
    :class:`GhIntegrationAutoMerger`.
    """

    def is_merged(self, pr_url: str) -> bool:
        """Return whether the given task PR is already merged.

        Delegates to :func:`agentrelay.ops.gh.pr_is_merged`, which returns
        ``False`` on subprocess failure rather than raising — safe for use
        in the probe's normalization path.
        """
        return gh.pr_is_merged(pr_url)

    def try_merge(self, pr_url: str) -> bool:
        """Best-effort merge of the given task PR.

        Wraps :func:`agentrelay.ops.gh.pr_merge` in a try/except so merge
        failures (conflicts, branch protection, transient network errors)
        return ``False`` instead of propagating a ``CalledProcessError``.
        The probe treats ``False`` as retry-eligible ``FAILED``, not as an
        internal error.
        """
        try:
            gh.pr_merge(pr_url)
            return True
        except subprocess.CalledProcessError:
            return False
