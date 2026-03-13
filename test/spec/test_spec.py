"""Tests for agentrelay.spec — SpecRepresentation protocol and PythonStubSpec."""

from __future__ import annotations

import pytest

from agentrelay.spec import PythonStubSpec, SpecRepresentation


class TestSpecRepresentation:
    """Tests for the SpecRepresentation protocol."""

    def test_python_stub_satisfies_protocol(self) -> None:
        """PythonStubSpec is a runtime-checkable SpecRepresentation."""
        spec = PythonStubSpec()
        assert isinstance(spec, SpecRepresentation)


class TestPythonStubSpec:
    """Tests for PythonStubSpec."""

    def test_default_construction(self) -> None:
        """Default include_type_hints is True."""
        spec = PythonStubSpec()
        assert spec.include_type_hints is True

    def test_name(self) -> None:
        """Name property returns 'python_stub'."""
        assert PythonStubSpec().name == "python_stub"

    def test_file_extensions(self) -> None:
        """File extensions returns ('.py',)."""
        assert PythonStubSpec().file_extensions == (".py",)

    def test_describe_for_spec_writer_mentions_not_implemented(self) -> None:
        """Spec writer description mentions NotImplementedError."""
        text = PythonStubSpec().describe_for_spec_writer()
        assert "NotImplementedError" in text

    def test_describe_for_spec_writer_type_hints_enabled(self) -> None:
        """Type hints instruction appears when include_type_hints=True."""
        text = PythonStubSpec(include_type_hints=True).describe_for_spec_writer()
        assert "type hints" in text.lower()

    def test_describe_for_spec_writer_type_hints_disabled(self) -> None:
        """Type hints marked optional when include_type_hints=False."""
        text = PythonStubSpec(include_type_hints=False).describe_for_spec_writer()
        assert "optional" in text.lower()

    def test_describe_for_consumer_mentions_docstrings(self) -> None:
        """Consumer description mentions docstrings."""
        text = PythonStubSpec().describe_for_consumer()
        assert "docstring" in text.lower()

    def test_frozen(self) -> None:
        """PythonStubSpec is immutable."""
        spec = PythonStubSpec()
        with pytest.raises(AttributeError):
            spec.include_type_hints = False  # type: ignore[misc]
