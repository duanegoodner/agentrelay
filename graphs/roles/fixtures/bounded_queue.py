"""BoundedQueue — a generic, fixed-capacity FIFO queue.

Fixture for concern-discovery experiments. Contains a deliberate contradiction:
the push() docstring body says it evicts the oldest item when full, but the
Raises section says it raises OverflowError when full.
"""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class BoundedQueue(Generic[T]):
    """A fixed-capacity FIFO queue.

    When the queue reaches capacity, push() automatically evicts the oldest
    (front) item to make room for the new item.

    Args:
        capacity: Maximum number of items. Must be a positive integer.

    Raises:
        ValueError: If capacity is not a positive integer.
    """

    def __init__(self, capacity: int) -> None:
        """Initialize the queue with a fixed capacity.

        Args:
            capacity: Maximum number of items. Must be a positive integer.

        Raises:
            ValueError: If capacity <= 0.
        """
        raise NotImplementedError

    def push(self, item: T) -> None:
        """Add an item to the back of the queue.

        If the queue is at capacity, the oldest (front) item is automatically
        evicted to make room for the new item.

        Args:
            item: The item to add.

        Raises:
            OverflowError: If the queue has reached capacity.
        """
        raise NotImplementedError

    def pop(self) -> T:
        """Remove and return the front item.

        Returns:
            The oldest item in the queue.

        Raises:
            IndexError: If the queue is empty.
        """
        raise NotImplementedError

    def peek(self) -> T:
        """Return the front item without removing it.

        Returns:
            The oldest item in the queue.

        Raises:
            IndexError: If the queue is empty.
        """
        raise NotImplementedError

    def is_full(self) -> bool:
        """Return True when the current length equals capacity."""
        raise NotImplementedError

    def __len__(self) -> int:
        """Return the current number of items in the queue."""
        raise NotImplementedError

    @property
    def capacity(self) -> int:
        """The maximum number of items the queue can hold (read-only)."""
        raise NotImplementedError
