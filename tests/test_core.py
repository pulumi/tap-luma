"""Tests standard tap features using the built-in SDK tests library."""

import os

import pytest
from singer_sdk.testing import get_tap_test_class

import tap_luma.client as client_module
from tap_luma.client import (
    RATE_LIMIT_MAX_TRIES,
    RATE_LIMIT_WAIT_SECONDS,
    REQUEST_INTERVAL_SECONDS,
)
from tap_luma.tap import TapLuma

API_KEY = os.environ.get("TAP_LUMA_API_KEY")

SAMPLE_CONFIG = {
    "api_key": API_KEY or "DUMMY_API_KEY",
    "scope": "calendar",
}


# The SDK's standard tests sync against the live API, so they only run when a
# real key is present (TAP_LUMA_API_KEY, wired in CI as a repository secret).
# Config-schema and discovery coverage without a key comes from the offline
# tests below.
TestTapLuma = pytest.mark.skipif(
    not API_KEY,
    reason="TAP_LUMA_API_KEY not set; the standard SDK tests sync live",
)(
    get_tap_test_class(
        tap_class=TapLuma,
        config=SAMPLE_CONFIG,
    )
)


def test_rate_limit_backoff_outlasts_the_window() -> None:
    """429s reject instantly until the window cools; waits must be window-sized."""
    stream = TapLuma(config=SAMPLE_CONFIG).streams["events"]
    assert stream.backoff_max_tries() == RATE_LIMIT_MAX_TRIES
    waits = stream.backoff_wait_generator()
    next(waits)  # the backoff decorator primes the generator; first yield is unused
    assert next(waits) == RATE_LIMIT_WAIT_SECONDS
    assert next(waits) == RATE_LIMIT_WAIT_SECONDS


def test_requests_are_throttled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request pauses afterwards: the rate budget is shared per API key."""
    sleeps = []
    monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        client_module.RESTStream, "_request", lambda _self, _pr, _ctx: "resp"
    )
    stream = TapLuma(config=SAMPLE_CONFIG).streams["events"]
    assert stream._request(None, None) == "resp"
    assert sleeps == [REQUEST_INTERVAL_SECONDS]
