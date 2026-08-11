"""REST client handling, including LumaStream base class.

The Luma public API (https://public-api.luma.com) is a straightforward REST API:
API-key auth via the ``x-luma-api-key`` header, list endpoints that return an
``entries[]`` array with cursor pagination (``has_more`` + ``next_cursor``, driven
by the ``pagination_cursor`` / ``pagination_limit`` query params). See
https://public-api.luma.com/openapi.json for the full spec.
"""

from __future__ import annotations

import decimal
import typing as t

from singer_sdk.authenticators import APIKeyAuthenticator
from singer_sdk.helpers.jsonpath import extract_jsonpath
from singer_sdk.pagination import BaseAPIPaginator
from singer_sdk.streams import RESTStream

if t.TYPE_CHECKING:
    import requests
    from singer_sdk.helpers.types import Context

DEFAULT_API_URL = "https://public-api.luma.com"
DEFAULT_PAGE_SIZE = 50


class LumaPaginator(BaseAPIPaginator):
    """Cursor paginator for Luma list endpoints.

    Luma responses carry ``has_more`` and ``next_cursor``; we feed the cursor back
    as the ``pagination_cursor`` query param until ``has_more`` is false.
    """

    def __init__(self) -> None:
        """Start with no cursor (first page)."""
        super().__init__(None)

    def get_next(self, response: requests.Response) -> str | None:
        """Return the next cursor, or ``None`` when the last page is reached.

        Args:
            response: The most recent API response.

        Returns:
            The ``next_cursor`` value while ``has_more`` is true, else ``None``.
        """
        body = response.json()
        if body.get("has_more"):
            return body.get("next_cursor")
        return None


class LumaStream(RESTStream):
    """Luma stream base class."""

    # Luma list endpoints wrap results in an ``entries`` array.
    records_jsonpath = "$.entries[*]"

    @property
    def url_base(self) -> str:
        """Return the API URL root, configurable via tap settings."""
        return self.config.get("api_url", DEFAULT_API_URL)

    @property
    def authenticator(self) -> APIKeyAuthenticator:
        """Return an API-key authenticator that sets the Luma auth header.

        Returns:
            An authenticator that injects ``x-luma-api-key`` on every request.
        """
        return APIKeyAuthenticator.create_for_stream(
            self,
            key="x-luma-api-key",
            value=self.config["api_key"],
            location="header",
        )

    @property
    def http_headers(self) -> dict:
        """Return the base HTTP headers.

        Returns:
            A dictionary of HTTP headers.
        """
        return {
            "User-Agent": f"{self.tap_name}/{self._tap.plugin_version}",
            "Accept": "application/json",
        }

    def get_new_paginator(self) -> BaseAPIPaginator:
        """Create a new cursor pagination helper.

        Returns:
            A :class:`LumaPaginator` instance.
        """
        return LumaPaginator()

    def get_url_params(
        self,
        context: Context | None,  # noqa: ARG002
        next_page_token: t.Any | None,  # noqa: ANN401
    ) -> dict[str, t.Any]:
        """Return the base pagination query params.

        Subclasses call ``super().get_url_params(...)`` and add their own filters
        (e.g. ``event_id`` for child streams, ``after`` for events).

        Args:
            context: The stream context.
            next_page_token: The next-page cursor, if any.

        Returns:
            A dictionary of URL query parameters.
        """
        params: dict[str, t.Any] = {
            "pagination_limit": self.config.get("page_size", DEFAULT_PAGE_SIZE),
        }
        if next_page_token:
            params["pagination_cursor"] = next_page_token
        return params

    def parse_response(self, response: requests.Response) -> t.Iterable[dict]:
        """Parse the response and return an iterator of result records.

        Args:
            response: The HTTP ``requests.Response`` object.

        Yields:
            Each record from the source.
        """
        yield from extract_jsonpath(
            self.records_jsonpath,
            input=response.json(parse_float=decimal.Decimal),
        )

    def post_process(
        self,
        row: dict,
        context: Context | None = None,  # noqa: ARG002
    ) -> dict | None:
        """As needed, append or transform raw data to match expected structure.

        Args:
            row: An individual record from the stream.
            context: The stream context.

        Returns:
            The updated record dictionary, or ``None`` to skip the record.
        """
        return row
