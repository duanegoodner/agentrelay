"""Example module demonstrating Google-style docstrings with mkdocstrings."""

from dataclasses import dataclass


@dataclass
class Greeter:
    """A simple greeter that produces greeting messages.

    Attributes:
        name: The name to greet.
        formal: If True, use a formal greeting style.
    """

    name: str
    formal: bool = False

    def greet(self) -> str:
        """Produce a greeting message.

        Returns:
            A greeting string addressed to this greeter's name.

        Examples:
            >>> Greeter(name="Alice").greet()
            'Hello, Alice!'
            >>> Greeter(name="Alice", formal=True).greet()
            'Good day, Alice.'
        """
        if self.formal:
            return f"Good day, {self.name}."
        return f"Hello, {self.name}!"
