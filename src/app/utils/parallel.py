"""Small helpers for splitting work across threads."""

from typing import Any, List, Sequence


def split_into_buckets(items: Sequence[Any], buckets: int) -> List[List[Any]]:
    """Split *items* into at most *buckets* contiguous, near-equal chunks.

    Returns ``[]`` for an empty input. The number of buckets never exceeds the
    number of items, so callers can size a thread pool with ``len(buckets)``.
    """
    items = list(items)
    if not items:
        return []
    buckets = max(1, min(int(buckets), len(items)))
    size = (len(items) + buckets - 1) // buckets
    return [items[i:i + size] for i in range(0, len(items), size)] or [items]
