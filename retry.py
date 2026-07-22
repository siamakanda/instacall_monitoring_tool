from __future__ import annotations

import time
import logging
from typing import Callable, TypeVar

T = TypeVar("T")


def _is_transient(error: str | None) -> bool:
    if not error:
        return False
    e = str(error).lower()
    return "timeout" in e or "connection" in e


def retry_with_backoff(
    fn: Callable[..., T],
    error_extractor: Callable[[T], str | None],
    *args: object,
    **kwargs: object,
) -> T:
    """Call fn, retry up to 2 times with escalating delay (2s, 5s) on transient failure.

    Args:
        fn: The function to call with retry logic.
        error_extractor: Takes fn's return value and returns an error string or None.
        *args, **kwargs: Passed through to fn.

    Returns:
        The result from fn (may be the errored result if all retries exhausted).
    """
    delays = [2, 5]
    result = fn(*args, **kwargs)
    error = error_extractor(result)
    attempt = 1

    while attempt <= len(delays) and _is_transient(error):
        logging.warning(f"Retry {attempt}/{len(delays) + 1} in {delays[attempt - 1]}s...")
        time.sleep(delays[attempt - 1])
        result = fn(*args, **kwargs)
        error = error_extractor(result)
        attempt += 1

    return result
