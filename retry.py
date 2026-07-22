import time
import logging


def _is_transient(error):
    if not error:
        return False
    e = str(error).lower()
    return "timeout" in e or "connection" in e


def retry_with_backoff(fn, error_extractor, *args, **kwargs):
    """Call fn, retry up to 2 times with escalating delay on transient failure.
    fn must accept (*args, **kwargs).
    error_extractor(fn_result) must return error string or None.
    Retries at 2s then 5s."""
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
