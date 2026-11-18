"""Thread-safe circuit breaker for flaky external or heavy operations.

A circuit breaker keeps the pipeline from hammering a backend that is known
to be failing (for example a broken PaddleOCR install or an out-of-memory
condition). After ``failure_threshold`` consecutive failures the breaker
opens and rejects calls immediately; once ``recovery_timeout`` seconds have
elapsed it allows a bounded number of trial calls (half-open). A successful
trial closes the breaker again, a failed trial re-opens it.

The implementation is thread-safe because OCR pages are predicted
concurrently from a thread pool.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected because the circuit breaker is open."""


class CircuitBreaker:
    """Track consecutive failures of one backend and fail fast while it is down.

    Args:
        name: Human-readable name used in logs and health output.
        failure_threshold: Consecutive failures that open the breaker.
        recovery_timeout: Seconds to wait before allowing a trial call.
        half_open_max_calls: Trial calls allowed while half-open.
        enabled: When false the breaker always allows requests (no-op mode).
        clock: Monotonic clock, injectable for tests.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        enabled: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout < 0:
            raise ValueError("recovery_timeout must be >= 0")

        self.name = name
        self.failure_threshold = int(failure_threshold)
        self.recovery_timeout = float(recovery_timeout)
        self.half_open_max_calls = max(1, int(half_open_max_calls))
        self.enabled = bool(enabled)

        self._clock = clock
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._half_open_calls = 0
        self._last_error: Optional[BaseException] = None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._refresh_state_locked()
            return self._state

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._consecutive_failures

    @property
    def last_error(self) -> Optional[BaseException]:
        with self._lock:
            return self._last_error

    def is_open(self) -> bool:
        """True while calls are being rejected (does not start a trial)."""
        if not self.enabled:
            return False
        with self._lock:
            if self._state is not CircuitState.OPEN:
                return False
            return not self._recovery_elapsed_locked()

    def snapshot(self) -> dict:
        """JSON-friendly state for logs and the ``/health`` endpoint."""
        with self._lock:
            self._refresh_state_locked()
            return {
                "name": self.name,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "last_error": str(self._last_error) if self._last_error else None,
            }

    # ------------------------------------------------------------------
    # Request gating
    # ------------------------------------------------------------------

    def allow_request(self) -> bool:
        """Whether a call may proceed, transitioning OPEN -> HALF_OPEN on timeout."""
        if not self.enabled:
            return True
        with self._lock:
            self._refresh_state_locked()
            if self._state is CircuitState.CLOSED:
                return True
            if self._state is CircuitState.OPEN:
                return False
            # HALF_OPEN: allow a bounded number of trial calls.
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    def record_success(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                logger.info("%s: trial call succeeded - closing circuit.", self.name)
            elif self._state is CircuitState.OPEN:
                # A call that was already in flight when the breaker opened.
                # Ignore it: in-flight successes must not flap the breaker.
                return
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._half_open_calls = 0
            self._last_error = None

    def record_failure(self, error: Optional[BaseException] = None) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._last_error = error
            if self._state is CircuitState.OPEN:
                return
            if self._state is CircuitState.HALF_OPEN:
                self._open_locked("trial call failed")
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._open_locked(
                    f"{self._consecutive_failures} consecutive failures"
                )

    def reset(self) -> None:
        """Force the breaker back to CLOSED (used by tests and operators)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._half_open_calls = 0
            self._last_error = None

    # ------------------------------------------------------------------
    # Convenience wrapper
    # ------------------------------------------------------------------

    def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run ``fn(*args, **kwargs)`` through the breaker."""
        if not self.allow_request():
            raise CircuitOpenError(f"{self.name} circuit breaker is open")
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - re-raised after accounting
            self.record_failure(exc)
            raise
        self.record_success()
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _recovery_elapsed_locked(self) -> bool:
        return self._clock() - self._opened_at >= self.recovery_timeout

    def _refresh_state_locked(self) -> None:
        if self._state is CircuitState.OPEN and self._recovery_elapsed_locked():
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0
            logger.info(
                "%s: recovery timeout elapsed - half-open for a trial call.",
                self.name,
            )

    def _open_locked(self, reason: str) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._half_open_calls = 0
        logger.error("%s: circuit opened (%s).", self.name, reason)
