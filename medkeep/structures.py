"""Hand-written linked containers. No built-in collection stores their items."""

from __future__ import annotations

from typing import Generic, Iterator, TypeVar

T = TypeVar("T")


class Link(Generic[T]):
    """One forward link; a Python reference is the node's address."""

    __slots__ = ("value", "next")

    def __init__(self, value: T) -> None:
        self.value = value
        self.next: Link[T] | None = None


class LinkedSequence(Generic[T]):
    """Append-only singly linked sequence used for verification/history results."""

    def __init__(self) -> None:
        self._head: Link[T] | None = None
        self._tail: Link[T] | None = None
        self._size = 0

    def append(self, value: T) -> None:
        node = Link(value)
        if self._tail is None:
            self._head = node
        else:
            self._tail.next = node
        self._tail = node
        self._size += 1

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[T]:
        node = self._head
        while node is not None:
            yield node.value
            node = node.next


class LinkedQueue(Generic[T]):
    """FIFO queue with explicit front/rear references and O(1) operations."""

    def __init__(self) -> None:
        self._front: Link[T] | None = None
        self._rear: Link[T] | None = None
        self._size = 0

    def enqueue(self, value: T) -> None:
        node = Link(value)
        if self._rear is None:
            self._front = node
        else:
            self._rear.next = node
        self._rear = node
        self._size += 1

    def peek(self) -> T:
        if self._front is None:
            raise IndexError("The request queue is empty.")
        return self._front.value

    def dequeue(self) -> T:
        if self._front is None:
            raise IndexError("The request queue is empty.")
        removed = self._front
        self._front = removed.next
        removed.next = None
        self._size -= 1
        if self._front is None:
            self._rear = None
        return removed.value

    def copy(self) -> LinkedQueue[T]:
        result: LinkedQueue[T] = LinkedQueue()
        for value in self:
            result.enqueue(value)
        return result

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[T]:
        node = self._front
        while node is not None:
            yield node.value
            node = node.next
