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
