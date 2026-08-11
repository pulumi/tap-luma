"""Stream type classes for tap-luma.

Field names mirror the Luma public API. Luma has no ``updated_since`` filter on
its list endpoints, so streams replicate in full and are deduplicated downstream
(matching the house convention of ``key-properties: []`` at the Meltano layer).

Schemas are intentionally minimal: the SDK passes undeclared fields straight
through to the target, so every real field still lands and can be modelled in the
data vault. The nested ``event`` object is passed through untyped. Enrich the
schemas (or set a natural sort/replication key) once the live response shapes are
confirmed against https://public-api.luma.com/openapi.json.
"""

from __future__ import annotations

import typing as t

from singer_sdk import typing as th
from singer_sdk.pagination import BaseAPIPaginator, SinglePagePaginator

from tap_luma.client import LumaStream

if t.TYPE_CHECKING:
    from singer_sdk.helpers.types import Context

# The events list wraps the full event object, whose shape is rich and varies by
# event type; pass it through untyped rather than enumerating every field.
_PASSTHROUGH_OBJECT = th.ObjectType(additional_properties=True)


class EventsStream(LumaStream):
    """Calendar (or organization) events -- the parent of guests & ticket types.

    Each entry wraps the event under ``event`` (name, ``start_at``, ``end_at``,
    geo/url, visibility, host counts, ...). ``api_id`` (evt-...) is the event key
    used to fetch child records.
    """

    name = "events"
    primary_keys = ("api_id",)
    replication_key = None

    schema = th.PropertiesList(
        th.Property(
            "api_id",
            th.StringType,
            required=True,
            description="Event id (evt-...).",
        ),
        th.Property(
            "event",
            _PASSTHROUGH_OBJECT,
            description="Full event object (name, start_at, end_at, geo, url, ...).",
        ),
        th.Property(
            "tags",
            th.ArrayType(_PASSTHROUGH_OBJECT),
            description="Event tags, when present.",
        ),
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
        event_id = record.get("api_id") or (record.get("event") or {}).get("api_id")
        return {"event_id": event_id}


class EventGuestsStream(LumaStream):
    """Guests (registrants / attendees) for each event -- the core attendance data.

    Includes ``approval_status`` (approved / pending_approval / declined / waitlist),
    registration and check-in timestamps, and the person's name/email.
    """

    name = "event_guests"
    parent_stream_type = EventsStream
    ignore_parent_replication_key = True
    path = "/v1/events/guests/list"
    primary_keys = ("api_id",)
    replication_key = None

    schema = th.PropertiesList(
        th.Property("api_id", th.StringType, description="Guest id."),
        th.Property(
            "event_id",
            th.StringType,
            description="Parent event id (FK, added by the tap).",
        ),
        th.Property("name", th.StringType),
        th.Property("email", th.StringType),
        th.Property(
            "approval_status",
            th.StringType,
            description="approved / pending_approval / declined / waitlist.",
        ),
        th.Property("registered_at", th.DateTimeType(nullable=True)),
        th.Property("checked_in_at", th.DateTimeType(nullable=True)),
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
    primary_keys = ("api_id",)
    replication_key = None

    schema = th.PropertiesList(
        th.Property("api_id", th.StringType, description="Ticket type id."),
        th.Property(
            "event_id",
            th.StringType,
            description="Parent event id (FK, added by the tap).",
        ),
        th.Property("name", th.StringType),
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
    primary_keys = ("api_id",)
    replication_key = None

    schema = th.PropertiesList(
        th.Property("api_id", th.StringType, description="Contact id."),
        th.Property("name", th.StringType),
        th.Property("email", th.StringType),
    ).to_dict()
