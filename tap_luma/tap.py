"""Luma tap class."""

from __future__ import annotations

from singer_sdk import Tap
from singer_sdk import typing as th

from tap_luma import streams


class TapLuma(Tap):
    """Singer tap for Luma (lu.ma) events data."""

    name = "tap-luma"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "api_key",
            th.StringType(nullable=False),
            required=True,
            secret=True,
            title="API Key",
            description=(
                "Luma API key, sent as the 'x-luma-api-key' header. Requires a "
                "Luma Plus plan; create one under Calendar Settings -> Developer "
                "-> API Keys (or the organization API settings)."
            ),
        ),
        th.Property(
            "api_url",
            th.StringType(nullable=False),
            default="https://public-api.luma.com",
            title="API URL",
            description="Base URL for the Luma public API.",
        ),
        th.Property(
            "scope",
            th.StringType(nullable=False),
            default="calendar",
            title="Scope",
            description=(
                "Whether the API key is scoped to a single 'calendar' or an "
                "'organization'. Controls which events endpoint is used."
            ),
            allowed_values=["calendar", "organization"],
        ),
        th.Property(
            "start_date",
            th.DateTimeType(nullable=True),
            title="Start Date",
            description=(
                "Only sync events occurring after this datetime (ISO 8601). Applied "
                "to the events list via the 'after' filter."
            ),
        ),
        th.Property(
            "page_size",
            th.IntegerType(nullable=True),
            default=50,
            title="Page Size",
            description="Number of records to request per page (pagination_limit).",
        ),
        additional_properties=False,
    ).to_dict()

    def discover_streams(self) -> list[streams.LumaStream]:
        """Return a list of discovered streams.

        Returns:
            A list of Luma streams.
        """
        return [
            streams.EventsStream(self),
            streams.EventGuestsStream(self),
            streams.EventTicketTypesStream(self),
            streams.PeopleStream(self),
        ]


if __name__ == "__main__":
    TapLuma.cli()
