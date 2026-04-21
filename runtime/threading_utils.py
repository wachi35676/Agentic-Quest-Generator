"""Background LLM call management with simple daemon threads."""

import threading
from typing import Any, Callable


class BackgroundTask:
    """Runs a callable in a daemon thread and stores the result.

    Usage:
        task = BackgroundTask(my_function, arg1, arg2)
        task.start()
        # ... later ...
        if task.is_done():
            result = task.get_result()
            error = task.get_error()
    """

    def __init__(self, func: Callable, *args, **kwargs):
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._result: Any = None
        self._error: Exception | None = None
        self._done = False
        self._thread: threading.Thread | None = None

    def start(self):
        """Start the background task."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        """Execute the callable and store the result or error."""
        try:
            self._result = self._func(*self._args, **self._kwargs)
        except Exception as e:
            self._error = e
        finally:
            self._done = True

    def is_done(self) -> bool:
        """Check if the task has completed (success or failure)."""
        return self._done

    def get_result(self) -> Any:
        """Get the result. Returns None if not done or if an error occurred."""
        return self._result

    def get_error(self) -> Exception | None:
        """Get the error if one occurred. Returns None if no error."""
        return self._error
