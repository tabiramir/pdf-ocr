"""Unit tests for the circuit breaker (no OCR dependencies required)."""

import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_breaker(clock=None, **kwargs) -> CircuitBreaker:
    return CircuitBreaker(
        "test",
        failure_threshold=kwargs.pop("failure_threshold", 3),
        recovery_timeout=kwargs.pop("recovery_timeout", 30.0),
        clock=clock or FakeClock(),
        **kwargs,
    )


def test_starts_closed_and_allows_requests():
    breaker = make_breaker()
    assert breaker.state is CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_opens_after_threshold_consecutive_failures():
    breaker = make_breaker()
    for _ in range(2):
        breaker.record_failure(RuntimeError("boom"))
    assert breaker.state is CircuitState.CLOSED

    breaker.record_failure(RuntimeError("boom"))
    assert breaker.state is CircuitState.OPEN
    assert breaker.is_open() is True
    assert breaker.allow_request() is False


def test_success_resets_failure_count():
    breaker = make_breaker()
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    assert breaker.consecutive_failures == 0

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is CircuitState.CLOSED


def test_half_open_after_recovery_timeout_and_success_closes():
    clock = FakeClock()
    breaker = make_breaker(clock=clock)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state is CircuitState.OPEN

    clock.advance(30.0)
    assert breaker.is_open() is False
    assert breaker.allow_request() is True
    assert breaker.state is CircuitState.HALF_OPEN

    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_half_open_trial_failure_reopens():
    clock = FakeClock()
    breaker = make_breaker(clock=clock)
    for _ in range(3):
        breaker.record_failure()

    clock.advance(30.0)
    assert breaker.allow_request() is True
    breaker.record_failure(RuntimeError("still broken"))
    assert breaker.state is CircuitState.OPEN
    assert breaker.allow_request() is False


def test_half_open_limits_trial_calls():
    clock = FakeClock()
    breaker = make_breaker(clock=clock, half_open_max_calls=1)
    for _ in range(3):
        breaker.record_failure()

    clock.advance(30.0)
    assert breaker.allow_request() is True  # consumes the single trial slot
    assert breaker.allow_request() is False


def test_call_wraps_exceptions_and_trips_breaker():
    breaker = make_breaker()

    def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        breaker.call(boom)
    assert breaker.consecutive_failures == 1


def test_call_rejected_when_open():
    breaker = make_breaker()
    for _ in range(3):
        breaker.record_failure()

    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: 1)


def test_disabled_breaker_always_allows():
    breaker = make_breaker(enabled=False)
    for _ in range(10):
        breaker.record_failure()

    assert breaker.state is CircuitState.CLOSED
    assert breaker.allow_request() is True
    assert breaker.call(lambda: 42) == 42


def test_thread_safety_of_failure_accounting():
    breaker = make_breaker(failure_threshold=5)

    def fail():
        breaker.record_failure(RuntimeError("parallel failure"))

    threads = [threading.Thread(target=fail) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert breaker.state is CircuitState.OPEN
    # Accounting stops once the breaker opens.
    assert breaker.consecutive_failures == 5


def test_snapshot_is_json_friendly():
    breaker = make_breaker()
    breaker.record_failure(RuntimeError("boom"))

    snap = breaker.snapshot()
    assert snap["name"] == "test"
    assert snap["state"] == "closed"
    assert snap["consecutive_failures"] == 1
    assert snap["last_error"] == "boom"
