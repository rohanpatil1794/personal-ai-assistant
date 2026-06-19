import time
from typing import Callable, TypeVar

from utils.logger import get_logger

log = get_logger(__name__)

T = TypeVar("T")


def with_retry(fn: Callable[..., T], *args, retries: int = 3, initial_delay: float = 1.0, **kwargs) -> T:
    """Call fn(*args, **kwargs) up to `retries` times with exponential backoff."""
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt == retries - 1:
                raise
            delay = initial_delay * (2 ** attempt)
            log.warning(
                "retry: attempt failed",
                fn=fn.__name__,
                attempt=attempt + 1,
                retries=retries,
                delay=delay,
                error=str(e),
            )
            time.sleep(delay)
