"""Spec representation protocol and concrete implementations.

Abstracts how specifications are presented to agents. Different languages
and paradigms represent specs differently; the :class:`SpecRepresentation`
protocol defines a common interface for describing spec format to role
templates and agents.

Protocols:
    SpecRepresentation: Abstract spec format description interface.

Classes:
    PythonStubSpec: Python stub files with docstrings + ``raise NotImplementedError``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class SpecRepresentation(Protocol):
    """Protocol for how specifications are represented to agents.

    Different languages and paradigms represent specs differently.  This
    protocol defines the interface for describing spec format to role
    templates and agents.
    """

    @property
    def name(self) -> str:
        """Human-readable name of this spec representation."""
        ...

    @property
    def file_extensions(self) -> tuple[str, ...]:
        """File extensions used by this spec type (e.g. ``('.py',)``)."""
        ...

    def describe_for_spec_writer(self) -> str:
        """Return instructions for how a spec_writer should create specs."""
        ...

    def describe_for_consumer(self) -> str:
        """Return instructions for how a test_writer/implementer reads specs."""
        ...


@dataclass(frozen=True)
class PythonStubSpec:
    """Python stub specification: files with docstrings + raise NotImplementedError.

    This is the default spec representation for Python projects.  Stub files
    contain class/function signatures with complete docstrings and
    ``raise NotImplementedError`` in all function bodies.

    Attributes:
        include_type_hints: Whether stubs should include type hints.
    """

    include_type_hints: bool = True

    @property
    def name(self) -> str:
        """Human-readable name of this spec representation."""
        return "python_stub"

    @property
    def file_extensions(self) -> tuple[str, ...]:
        """File extensions used by this spec type."""
        return (".py",)

    def describe_for_spec_writer(self) -> str:
        """Instructions for creating Python stub specs."""
        hints = (
            "Include type hints on all function signatures and return types."
            if self.include_type_hints
            else "Type hints are optional."
        )
        return (
            "Create Python files with class and function signatures.\n"
            "Each function body must be exactly `raise NotImplementedError`.\n"
            "Write complete docstrings (Args, Returns, Raises sections) for "
            "every public function and class.\n"
            f"{hints}\n"
            "Do NOT implement any logic — only define the API contract."
        )

    def describe_for_consumer(self) -> str:
        """Instructions for reading Python stub specs."""
        return (
            "The specification is expressed as Python stub files.\n"
            "Docstrings are the authoritative spec — read them carefully.\n"
            "Function signatures define the API contract (names, parameters, "
            "return types).\n"
            "Bodies containing `raise NotImplementedError` indicate functions "
            "that are not yet implemented."
        )


__all__ = [
    "PythonStubSpec",
    "SpecRepresentation",
]
