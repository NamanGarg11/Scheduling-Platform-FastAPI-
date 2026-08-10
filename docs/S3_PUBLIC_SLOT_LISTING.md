# S3 — Public Slot Listing

**Status: Complete.** Consumes the slot inventory produced by S2 regeneration; it is a
**read-only availability projection** — no generation, no reconciliation, no mutation.

## Endpoint

```
GET /api/public/users/{user_id}/event-types/{slug}/slots
```

Query parameters:

| param       | type   | required | default                                        |
| ----------- | ------ | -------- | ---------------------------------------------- |
| `from_date` | `date` | no       | today (in the resolved timezone)               |
| `to_date`   | `date` | no       | `from_date + SLOT_GENERATION_DAYS - 1` (30 days) |
| `timezone`  | `str`  | no       | the host's timezone                            |

This endpoint is **intentionally public** (no auth header, no host identity). All other
endpoints remain protected as before; nothing is weakened.

## Flow

```
Public Client
     │  GET /api/public/users/{user}/event-types/{slug}/slots
     ▼
PublicSlotService
     ├── Resolve user (404 if missing)
     ├── Resolve event type by (user_id, slug) — slug alone is never trusted
     │     └── missing / belongs to another user / inactive → 404 (no existence leak)
     ├── Resolve timezone (requested, else host's; invalid → 400)
     ├── Resolve default range, validate from <= to, enforce 62-day cap (400)
     ├── Convert [from 00:00, (to+1) 00:00) local → UTC boundaries
     ▼
SlotRepository.find_available_for_event_type_in_range
     │   WHERE event_type_id = ? AND start_at >= ? AND start_at < ?
     │         AND status = 'AVAILABLE'  ORDER BY start_at
     ▼
AVAILABLE persisted slots
     ▼
Past slots (start_at <= now) excluded
     ▼
Group by local calendar day in the resolved timezone
     ▼
UTC timestamps + local-day grouping
```

## Date-range semantics

- `from_date`/`to_date` are **inclusive** host/requested-local calendar dates, expanded to
  `[from 00:00, (to+1) 00:00)` in the resolved timezone, then converted to UTC for the query —
  identical semantics to S2 regeneration (ADR-021).
- Hard maximum: `to_date - from_date <= 62 days` (ADR-017). Exceeding it returns `400` via the
  centralized validation envelope — never silently truncated.
- `from_date > to_date` → `400`.

## Timezone semantics

- Slots are stored as **UTC instants** (S2). The API returns those same UTC instants.
- Grouping is by **local calendar day** in the resolved timezone — never the UTC date.

Example (host `Asia/Kolkata`):

| UTC instant                 | Kolkata local | grouping day (Kolkata) |
| --------------------------- | ------------- | ---------------------- |
| `2026-08-09T20:30:00Z`      | `02:00 IST`   | `2026-08-10`           |

The same slot requested with `timezone=UTC` groups under `2026-08-09`. The returned
`start_at`/`end_at` are identical in both views — the grouping key is local, the timestamps
stay UTC.

## Visibility rules

- Only `AVAILABLE` slots are returned. `BLOCKED` and `BOOKED` rows are never exposed, even if
  they exist inside the range (S3 filters independently of S2 reconciliation).
- No booking IDs, hosts, blocking reasons, exceptions, or internal metadata are included.
  The event-type summary exposes only `id`, `slug`, `title`.
- Past slots (`start_at <= now`) are excluded.

## Response shape

```json
{
  "event_type": { "id": "...", "slug": "...", "title": "..." },
  "timezone": "Asia/Kolkata",
  "days": [
    {
      "date": "2026-08-10",
      "slots": [
        { "start_at": "2026-08-09T20:30:00Z", "end_at": "2026-08-09T21:00:00Z" }
      ]
    }
  ]
}
```

A valid request with no available slots returns `200` with `"days": []` — never `404`.

## Guarantees and non-guarantees

- **Read-only:** the endpoint performs no `INSERT`/`UPDATE`/`DELETE`, no regeneration, no
  reconciliation, no exception processing, no reservation.
- **No reservation guarantee:** a slot shown may be booked by someone else before the caller
  acts. Final availability validation belongs to the booking transaction (unchanged).
- **Stale inventory:** if the host has not run regeneration, the endpoint reports whatever is
  persisted — it does not silently generate.

## Database

No schema change. The query is served by the existing unique index
`uq_slot_event_type_start_end (event_type_id, start_at, end_at)` — verified with
`EXPLAIN (FORMAT JSON)` in `tests/e2e/test_public_slots_api.py` (one-day window from a
~372-row table → index scan).

## Tests

- `tests/slots/test_public_slots_service.py` (12, DB-free): default/explicit range, 62-day
  cap, timezone conversion, cross-day grouping with UTC timestamps, past filtering, 404s,
  empty result.
- `tests/e2e/test_public_slots_api.py` (12, real Postgres): happy path, missing user / event
  type / wrong owner / inactive, 400s (range, 62-day, invalid timezone), BLOCKED/BOOKED
  omission, cross-day grouping, EXPLAIN index verification.
