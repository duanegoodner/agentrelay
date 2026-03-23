"""Tests for BoundedQueue — expects OverflowError on push-when-full.

Fixture for concern-discovery experiments. These tests are written against the
OverflowError interpretation of push(). The stub docstring body says push()
evicts the oldest item instead. Agents should discover this contradiction.
"""

from __future__ import annotations

import pytest
from agentrelaydemos.bounded_queue import BoundedQueue


class TestBoundedQueueInit:
    def test_creates_empty_queue(self) -> None:
        q: BoundedQueue[int] = BoundedQueue(3)
        assert len(q) == 0

    def test_capacity_property(self) -> None:
        q: BoundedQueue[int] = BoundedQueue(5)
        assert q.capacity == 5

    def test_rejects_zero_capacity(self) -> None:
        with pytest.raises(ValueError):
            BoundedQueue(0)

    def test_rejects_negative_capacity(self) -> None:
        with pytest.raises(ValueError):
            BoundedQueue(-1)


class TestPush:
    def test_push_single_item(self) -> None:
        q: BoundedQueue[str] = BoundedQueue(3)
        q.push("a")
        assert len(q) == 1

    def test_push_to_capacity(self) -> None:
        q: BoundedQueue[int] = BoundedQueue(2)
        q.push(1)
        q.push(2)
        assert len(q) == 2

    def test_push_when_full_raises_overflow(self) -> None:
        q: BoundedQueue[int] = BoundedQueue(2)
        q.push(1)
        q.push(2)
        with pytest.raises(OverflowError):
            q.push(3)


class TestPop:
    def test_pop_returns_oldest(self) -> None:
        q: BoundedQueue[str] = BoundedQueue(3)
        q.push("a")
        q.push("b")
        assert q.pop() == "a"

    def test_pop_decreases_length(self) -> None:
        q: BoundedQueue[int] = BoundedQueue(3)
        q.push(1)
        q.push(2)
        q.pop()
        assert len(q) == 1

    def test_pop_empty_raises_index_error(self) -> None:
        q: BoundedQueue[int] = BoundedQueue(3)
        with pytest.raises(IndexError):
            q.pop()


class TestPeek:
    def test_peek_returns_front_without_removing(self) -> None:
        q: BoundedQueue[str] = BoundedQueue(3)
        q.push("a")
        q.push("b")
        assert q.peek() == "a"
        assert len(q) == 2

    def test_peek_empty_raises_index_error(self) -> None:
        q: BoundedQueue[int] = BoundedQueue(3)
        with pytest.raises(IndexError):
            q.peek()


class TestIsFull:
    def test_not_full_when_empty(self) -> None:
        q: BoundedQueue[int] = BoundedQueue(3)
        assert not q.is_full()

    def test_full_at_capacity(self) -> None:
        q: BoundedQueue[int] = BoundedQueue(2)
        q.push(1)
        q.push(2)
        assert q.is_full()
