import signal
import time
from contextlib import contextmanager
from typing import Callable, Optional

class TimeoutError(Exception):
    """Exception raised when a function times out."""
    pass

class WallTimeTracker:
    """Tracks elapsed wall time and enforces a time limit."""

    def __init__(self, wall_time_limit: int):
        """Initialize the wall time tracker.

        Args:
            wall_time_limit: Maximum allowed time in seconds
        """
        self.wall_time_limit = wall_time_limit
        self.start_time = time.time()

    def elapsed(self) -> float:
        """Get elapsed time since initialization.

        Returns:
            Elapsed time in seconds
        """
        return time.time() - self.start_time

    def remaining(self) -> float:
        """Get remaining time before limit is reached.

        Returns:
            Remaining time in seconds
        """
        return max(0, self.wall_time_limit - self.elapsed())

    def is_expired(self) -> bool:
        """Check if the time limit has been reached.

        Returns:
            True if time limit has been reached, False otherwise
        """
        return self.elapsed() >= self.wall_time_limit

    def percentage_used(self) -> float:
        """Get percentage of time limit used.

        Returns:
            Percentage of time limit used
        """
        return min(100, (self.elapsed() / self.wall_time_limit) * 100)


@contextmanager
def timeout(seconds: int, on_timeout: Optional[Callable] = None):
    """Context manager that raises a TimeoutError if the enclosed block
    takes longer than the specified number of seconds to execute.

    Args:
        seconds: Timeout in seconds
        on_timeout: Optional callback to execute when timeout occurs

    Raises:
        TimeoutError: If the enclosed block takes longer than seconds to execute
    """
    def timeout_handler(signum, frame):
        if on_timeout:
            on_timeout()
        raise TimeoutError(f"Function timed out after {seconds} seconds")

    # Set the timeout handler
    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, timeout_handler)

    # Set the alarm
    signal.alarm(seconds)
    try:
        yield
    finally:
        # Cancel the alarm and restore the previous handler
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def setup_wall_time_limit(seconds: int, on_timeout: Optional[Callable] = None):
    """Set up a process-wide wall time limit using the SIGALRM signal.

    Args:
        seconds: Wall time limit in seconds
        on_timeout: Optional callback to execute when timeout occurs
    """
    def alarm_handler(signum, frame):
        if on_timeout:
            on_timeout()
        raise TimeoutError(f"Process exceeded wall time limit of {seconds} seconds")

    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(seconds)
