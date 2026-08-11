# tap-luma

A [Singer](https://singer.io) tap for [Luma (lu.ma)](https://luma.com) events,
built with the [Meltano Singer SDK](https://sdk.meltano.com).

It mirrors a Luma calendar (or organization) into your warehouse: events and,
per event, their guests (registrants/attendees) and ticket types, plus the
calendar's contacts.

## Requirements

A Luma **API key** (requires a Luma Plus plan). Create one under
**Calendar Settings → Developer → API Keys** (calendar scope) or the
organization API settings. The key is sent as the `x-luma-api-key` header.

## Streams

| Stream | Endpoint | Notes |
| --- | --- | --- |
| `events` | `GET /v1/calendars/events/list` (or `/v1/organizations/events/list`) | Parent stream. Filtered by `after` = `start_date`. |
| `event_guests` | `GET /v1/events/guests/list` | Child of `events`. Registrants/attendees + `approval_status`, `event_id` FK added by the tap. |
| `event_ticket_types` | `GET /v1/events/ticket-types/list` | Child of `events`. `event_id` FK added by the tap. |
| `people` | `GET /v1/calendars/contacts/list` | Calendar contacts / audience. |

Luma list endpoints use cursor pagination (`pagination_cursor` / `pagination_limit`
with `has_more` + `next_cursor`) and have no `updated_since` filter, so streams
replicate in full and are deduplicated downstream.

See the full API spec at <https://public-api.luma.com/openapi.json>.

## Configuration

| Setting | Required | Default | Description |
| --- | --- | --- | --- |
| `api_key` | yes | — | Luma API key (sent as `x-luma-api-key`). |
| `api_url` | no | `https://public-api.luma.com` | API base URL. |
| `scope` | no | `calendar` | `calendar` or `organization` — selects the events endpoint. |
| `start_date` | no | — | Only sync events after this datetime (ISO 8601). |
| `page_size` | no | `50` | Records per page (`pagination_limit`). |

Run `tap-luma --about --format=markdown` for the full config reference.

## Usage

```bash
# with uv (recommended)
uv run tap-luma --version
uv run tap-luma --about --format=json

# discovery / sync (config.json holds api_key etc.)
uv run tap-luma --config config.json --discover > catalog.json
uv run tap-luma --config config.json
```

### With Meltano (local dev)

```bash
export TAP_LUMA_API_KEY='...'
meltano install
meltano run tap-luma target-jsonl
```

## Developing

```bash
uv sync
uv run --group test pytest
uvx ruff check .
```
