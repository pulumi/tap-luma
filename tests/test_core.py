"""Tests standard tap features using the built-in SDK tests library."""

from singer_sdk.testing import get_tap_test_class

from tap_luma.tap import TapLuma

SAMPLE_CONFIG = {
    "api_key": "DUMMY_API_KEY",
    "scope": "calendar",
}


# Run standard built-in tap tests from the SDK. Offline tests (config schema,
# discovery) run without credentials; tests that require a live connection use a
# real key passed via TAP_LUMA_* environment variables (see tox.ini).
TestTapLuma = get_tap_test_class(
    tap_class=TapLuma,
    config=SAMPLE_CONFIG,
)


def test_rate_limit_backoff_outlasts_the_window():
    """429s reject instantly until the window cools; waits must be window-sized."""
    from tap_luma.client import RATE_LIMIT_MAX_TRIES, RATE_LIMIT_WAIT_SECONDS

    stream = TapLuma(config=SAMPLE_CONFIG).streams["events"]
    assert stream.backoff_max_tries() == RATE_LIMIT_MAX_TRIES
    waits = stream.backoff_wait_generator()
    next(waits)  # the backoff decorator primes the generator; first yield is discarded
    assert next(waits) == RATE_LIMIT_WAIT_SECONDS
    assert next(waits) == RATE_LIMIT_WAIT_SECONDS


def test_requests_are_throttled(monkeypatch):
    """Every request pauses afterwards: the rate budget is shared per API key."""
    import tap_luma.client as client_module

    sleeps = []
    monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        client_module.RESTStream, "_request", lambda self, pr, ctx: "resp"
    )
    stream = TapLuma(config=SAMPLE_CONFIG).streams["events"]
    assert stream._request(None, None) == "resp"
    assert sleeps == [client_module.REQUEST_INTERVAL_SECONDS]
