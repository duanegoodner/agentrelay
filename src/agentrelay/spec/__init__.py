"""Spec representation protocol and concrete implementations.

Abstracts how specifications are presented to agents.  Different languages
and paradigms represent specs differently; the :class:`SpecRepresentation`
protocol defines a common interface.
"""

from agentrelay.spec.spec import PythonStubSpec, SpecRepresentation

__all__ = [
    "PythonStubSpec",
    "SpecRepresentation",
]
