"""Per-extraction cancellation checks, isolated across concurrent worker contexts."""
from contextvars import ContextVar
from typing import Callable, Optional


cancel_requested: ContextVar[Optional[Callable[[], bool]]] = ContextVar("cancel_requested", default=None)


class ExtractionCancelled(RuntimeError):
    pass


def check_cancelled() -> None:
    check = cancel_requested.get()
    if check is not None and check():
        raise ExtractionCancelled("Extraction cancelled by the author.")
