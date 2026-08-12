"""Stream type classes for tap-luma.

Field names mirror the Luma public API (verified against live responses). Luma has
no ``updated_since`` filter on its list endpoints, so streams replicate in full and
are deduplicated downstream (matching the house convention of ``key-properties: []``
at the Meltano layer).

Each list endpoint returns a flat ``entries[]`` array; the entity key is ``id``
(``evt-...`` events, ``gst-...`` guests, ``evtticktyp-...`` ticket types). Nested
objects/arrays (geo, coordinate, event_tickets, registration_*) are passed through
untyped so nothing is lost. See https://public-api.luma.com/openapi.json.
"""

from __future__ import annotations

import typing as t

from singer_sdk import typing as th
from singer_sdk.pagination import BaseAPIPaginator, SinglePagePaginator

from tap_luma.client import LumaStream

if t.TYPE_CHECKING:
    from singer_sdk.helpers.types import Context

# Nested blobs (geo/coordinate/tickets/answers) vary per event; pass them through.
_PASSTHROUGH_OBJECT = th.ObjectType(additional_properties=True)


class EventsStream(LumaStream):
    """Calendar (or organization) events -- the parent of guests & ticket types.

    Entries are flat event objects keyed by ``id`` (evt-...): name, start/end,
    location, geo, cover, host user, registration questions, etc.
    """

    name = "events"
    primary_keys = ("id",)
    replication_key = None

    schema = th.PropertiesList(
        th.Property("id", th.StringType, required=True, description="Event id (evt-...)."),
        th.Property("calendar_id", th.StringType(nullable=True)),
        th.Property("user_id", th.StringType(nullable=True), description="Host/creator user id."),
        th.Property("name", th.StringType(nullable=True)),
        th.Property("start_at", th.DateTimeType(nullable=True)),
        th.Property("end_at", th.DateTimeType(nullable=True)),
        th.Property("created_at", th.DateTimeType(nullable=True)),
        th.Property("duration_interval", th.StringType(nullable=True), description="ISO 8601 duration."),
        th.Property("timezone", th.StringType(nullable=True)),
        th.Property("location_type", th.StringType(nullable=True), description="offline / online / ..."),
        th.Property("location_visibility", th.StringType(nullable=True)),
        th.Property("meeting_url", th.StringType(nullable=True)),
        th.Property("cover_url", th.StringType(nullable=True)),
        th.Property("url", th.StringType(nullable=True)),
        th.Property("geo_address_json", _PASSTHROUGH_OBJECT, description="Address detail object."),
        th.Property("coordinate", _PASSTHROUGH_OBJECT, description="{longitude, latitude}."),
        th.Property("registration_questions", th.ArrayType(_PASSTHROUGH_OBJECT)),
    ).to_dict()

    @property
    def path(self) -> str:
        """Return the events list path for the configured scope."""
        if self.config.get("scope", "calendar") == "organization":
            return "/v1/organizations/events/list"
        return "/v1/calendars/events/list"

    def get_url_params(
        self,
        context: Context | None,
        next_page_token: t.Any | None,  # noqa: ANN401
    ) -> dict[str, t.Any]:
        """Add the ``after`` (start_date) filter to the base pagination params.

        Args:
            context: The stream context.
            next_page_token: The next-page cursor, if any.

        Returns:
            A dictionary of URL query parameters.
        """
        params = super().get_url_params(context, next_page_token)
        start_date = self.config.get("start_date")
        if start_date:
            params["after"] = start_date
        return params

    def get_child_context(
        self,
        record: dict,
        context: Context | None,  # noqa: ARG002
    ) -> dict:
        """Return the context (``event_id``) passed to child streams.

        Args:
            record: An event entry.
            context: The parent stream context.

        Returns:
            A context dict carrying the event id for child streams.
        """
        return {"event_id": record["id"]}


class EventGuestsStream(LumaStream):
    """Guests (registrants / attendees) for each event -- the core attendance data.

    Keyed by ``id`` (gst-...). Includes ``approval_status`` (approved /
    pending_approval / declined / waitlist), registration/invite/join timestamps,
    the person (``user_email`` / ``user_name``), and their ``event_tickets``.
    """

    name = "event_guests"
    parent_stream_type = EventsStream
    ignore_parent_replication_key = True
    path = "/v1/events/guests/list"
    primary_keys = ("id",)
    replication_key = None

    schema = th.PropertiesList(
        th.Property("id", th.StringType, description="Guest id (gst-...)."),
        th.Property(
            "event_id",
            th.StringType,
            description="Parent event id (FK, added by the tap).",
        ),
        th.Property("user_id", th.StringType(nullable=True)),
        th.Property("user_email", th.StringType(nullable=True)),
        th.Property("user_name", th.StringType(nullable=True)),
        th.Property("user_first_name", th.StringType(nullable=True)),
        th.Property("user_last_name", th.StringType(nullable=True)),
        th.Property(
            "approval_status",
            th.StringType,
            description="approved / pending_approval / declined / waitlist.",
        ),
        th.Property("registered_at", th.DateTimeType(nullable=True)),
        th.Property("invited_at", th.DateTimeType(nullable=True)),
        th.Property("joined_at", th.DateTimeType(nullable=True)),
        th.Property("phone_number", th.StringType(nullable=True)),
        th.Property("registration_answers", th.ArrayType(_PASSTHROUGH_OBJECT)),
        th.Property(
            "event_tickets",
            th.ArrayType(_PASSTHROUGH_OBJECT),
            description="Per-guest tickets incl. amount, currency, checked_in_at.",
        ),
    ).to_dict()

    def get_url_params(
        self,
        context: Context | None,
        next_page_token: t.Any | None,  # noqa: ANN401
    ) -> dict[str, t.Any]:
        """Add the parent ``event_id`` to the base pagination params.

        Args:
            context: The child context carrying ``event_id``.
            next_page_token: The next-page cursor, if any.

        Returns:
            A dictionary of URL query parameters.
        """
        params = super().get_url_params(context, next_page_token)
        params["event_id"] = (context or {})["event_id"]
        return params

    def post_process(
        self,
        row: dict,
        context: Context | None = None,
    ) -> dict | None:
        """Stamp the parent event id onto each guest record.

        Args:
            row: A guest record.
            context: The child context carrying ``event_id``.

        Returns:
            The record with ``event_id`` populated.
        """
        row["event_id"] = (context or {}).get("event_id")
        return row


class EventTicketTypesStream(LumaStream):
    """Ticket types (price tiers) per event. Not cursor-paginated."""

    name = "event_ticket_types"
    parent_stream_type = EventsStream
    ignore_parent_replication_key = True
    path = "/v1/events/ticket-types/list"
    primary_keys = ("id",)
    replication_key = None

    schema = th.PropertiesList(
        th.Property("id", th.StringType, description="Ticket type id (evtticktyp-...)."),
        th.Property(
            "event_id",
            th.StringType,
            description="Parent event id (FK, added by the tap).",
        ),
        th.Property("name", th.StringType(nullable=True)),
        th.Property("type", th.StringType(nullable=True), description="free / paid / donation."),
        th.Property("cents", th.IntegerType(nullable=True)),
        th.Property("min_cents", th.IntegerType(nullable=True)),
        th.Property("currency", th.StringType(nullable=True)),
        th.Property("require_approval", th.BooleanType(nullable=True)),
        th.Property("is_hidden", th.BooleanType(nullable=True)),
        th.Property("max_capacity", th.IntegerType(nullable=True)),
    ).to_dict()

    def get_new_paginator(self) -> BaseAPIPaginator:
        """Ticket types return a single, un-paginated ``entries`` array.

        Returns:
            A single-page paginator.
        """
        return SinglePagePaginator()

    def get_url_params(
        self,
        context: Context | None,
        next_page_token: t.Any | None,  # noqa: ARG002, ANN401
    ) -> dict[str, t.Any]:
        """Return just the parent ``event_id`` (no pagination params).

        Args:
            context: The child context carrying ``event_id``.
            next_page_token: Unused (single page).

        Returns:
            A dictionary of URL query parameters.
        """
        return {"event_id": (context or {})["event_id"]}

    def post_process(
        self,
        row: dict,
        context: Context | None = None,
    ) -> dict | None:
        """Stamp the parent event id onto each ticket-type record.

        Args:
            row: A ticket-type record.
            context: The child context carrying ``event_id``.

        Returns:
            The record with ``event_id`` populated.
        """
        row["event_id"] = (context or {}).get("event_id")
        return row


class PeopleStream(LumaStream):
    """Calendar contacts -- the audience/people who registered or subscribed."""

    name = "people"
    path = "/v1/calendars/contacts/list"
    primary_keys = ("id",)
    replication_key = None

    schema = th.PropertiesList(
        th.Property("id", th.StringType, description="Contact id."),
        th.Property("user_id", th.StringType(nullable=True)),
        th.Property("email", th.StringType(nullable=True)),
        th.Property("name", th.StringType(nullable=True)),
    ).to_dict()
