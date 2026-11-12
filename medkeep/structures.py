from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class Link(Generic[T]):
    __slots__ = ("value", "next")

    def __init__(self, value=None):
        self.value = value
        self.next = None


class LinkedSequence(Generic[T]):
    def __init__(self):
        self._head = None
        self._tail = None
        self._size = 0

    def append(self, value: T):
        new_node = Link()
        new_node.value = value
        if self._tail is None:
            self._head = new_node
        else:
            self._tail.next = new_node
        self._tail = new_node
        self._size += 1

    def __len__(self):
        return self._size

    def __iter__(self):
        current_node = self._head
        while current_node is not None:
            yield current_node.value
            current_node = current_node.next


class LinkedQueue(Generic[T]):
    def __init__(self):
        self._front = None
        self._rear = None
        self._size = 0

    def enqueue(self, value: T):
        new_node = Link()
        new_node.value = value
        if self._rear is None:
            self._front = new_node
        else:
            self._rear.next = new_node
        self._rear = new_node
        self._size += 1

    def peek(self):
        if self._front is None:
            raise IndexError("The request queue is empty.")
        return self._front.value

    def dequeue(self):
        if self._front is None:
            raise IndexError("The request queue is empty.")
        front_node = self._front
        self._front = front_node.next
        front_node.next = None
        self._size -= 1
        if self._front is None:
            self._rear = None
        return front_node.value

    def copy(self):
        copied_queue = LinkedQueue()
        for value in self:
            copied_queue.enqueue(value)
        return copied_queue

    def __len__(self):
        return self._size

    def __iter__(self):
        current_node = self._front
        while current_node is not None:
            yield current_node.value
            current_node = current_node.next
