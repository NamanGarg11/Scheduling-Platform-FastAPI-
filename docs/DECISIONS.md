# Scheduling Platform — Architecture Decisions

This file records architectural contracts for **slot generation, regeneration, and public slot
listing** (Phases S1–S3). Decisions here are normative: tests and code must not drift from them
without a new entry superseding them. The booking engine is complete and frozen
(`docs/BOOKING_ENGINE_REPORT.md`); it is out of scope unless a later integration test exposes a
regression.

Status meanings:

- **Accepted** — locked, normative. Code and tests must conform.
- **Provisional** — expected to change in a named phase; recorded so the intent is explicit.

---

## ADR-001 — Half-open interval semantics

**Status: Accepted**

All time intervals in the engine are half-open `[start, end)`.

- Two intervals overlap iff `a.start < b.end and b.start < a.end`.
- Touching (one ends exactly when the next starts) is **not** overlap.

Rationale: adjacent slots (`09:00–10:00`, `10:00–11:00`) tile without double-counting, and the
rule makes boundary math exact at window edges and around DST transitions.

## ADR-002 — Touching windows merge

**Status: Accepted**

`merge_windows` sorts windows by start and merges when `next.start <= current.end` — touching
windows merge. This normalizes fragmented availability
(`09:00–12:00 + 11:30–15:00 + 15:00–17:00 → 09:00–17:00`) before slot splitting, preventing
duplicate/fragmented candidates.

## ADR-003 — Slot stepping arithmetic (normative — do not "fix")

**Status: Accepted**

Given window `[W_start, W_end)`, duration `D`, `buffer_before = B`, `buffer_after = A`:

```
occupied = B + D + A
cursor   = W_start
while cursor + occupied <= W_end:
    emit meeting [cursor + B, cursor + B + D)
    cursor += occupied
```

Consequences:

- Adjacent candidates tile — candidate N's before-buffer is candidate N−1's after-buffer.
  Buffers are **shared** between consecutive meetings, which is the correct single-host behavior.
- The existing test `tests/slots/test_generation.py::test_generates_slots_with_buffers` is the
  specification: `09:00–12:00`, `D=30`, `B=5`, `A=10` → exactly **4** candidates starting
  `09:05, 09:50, 10:35, 11:20`. It must not be "improved" into a 5-slot maximal-packing
  interpretation.
- The stepping loop is **anchored in UTC**: the window is converted to UTC instants at the
  boundary, the cursor advances by `occupied` in UTC, and each candidate is converted back to
  the host's local zone for output. On days without a DST transition this is byte-identical to
  wall-clock stepping (the pinned 4-slot example is unchanged). Across a spring-forward gap it
  is the only correct option: wall-clock stepping folds the cursor back onto earlier UTC
  intervals, producing duplicated, out-of-order slots (verified empirically, S1 spec
  §Stepping anchor). Resolving each cursor through the DST resolver does **not** fix this — the
  fold happens because the next wall-clock cursor (e.g. `02:00`) resolves to an *earlier* UTC
  instant than the previous one.

## ADR-004 — Buffer semantics

**Status: Accepted**

- A candidate's **occupied** interval is `[start − B, end + A)`.
- The **stored/listed** slot is the actual meeting `[start, end)`.
- All collision checks (existing bookings, other occupied slots) use occupied intervals;
  persistence and the public API use meeting intervals.
- The unique constraint `(event_type_id, start_at, end_at)` keys on meeting intervals.

## ADR-005 — DST: nonexistent local times (spring forward)

**Status: Accepted**

Example: Europe/London 2026-03-29, `01:00 GMT → 02:00 BST`; local `01:30` does not exist.

Decision: a nonexistent wall time resolves to the UTC instant the wall clock would have reached
had no jump occurred — equivalently, the wall time shifts forward by the gap
(`01:30 → 02:30 BST = 01:30 UTC`). This matches Python `zoneinfo`'s default gap resolution
(pre-gap offset) and matches what a meeting at that wall time actually does in practice.

The engine makes this resolution explicit (no reliance on implicit defaults) and tests it.

## ADR-006 — DST: ambiguous local times (autumn back)

**Status: Accepted**

Example: Europe/London 2026-10-25, `02:00 BST → 01:00 GMT`; local `01:30` occurs twice
(`01:30 BST = 00:30 UTC`, then `01:30 GMT = 01:30 UTC`).

Decision: **`fold=0`** — the first occurrence (BST, UTC+1). This is Python's default and the
least surprising for invitees. Explicit `fold` is set in the engine, and both occurrences are
tested.

## ADR-007 — DST handled in the pure engine

**Status: Accepted**

All local→UTC resolution happens inside `app/slots/slot_generation.py` via
`zoneinfo.ZoneInfo`. The engine never performs naive UTC arithmetic on availability windows. The
orchestrator passes the host's IANA timezone string and receives aware datetimes; the engine is
the only component that knows about timezones.

The engine emits aware datetimes in the **host's local zone** (this is what the existing stepping
test pins: `start_at.hour == 9` for Asia/Kolkata). The orchestrator converts to UTC at the
persistence boundary (ADR-009). `fold` is set explicitly via `time.replace(fold=...)` before
`datetime.combine` — `combine` itself does not accept a `fold` argument.

## ADR-008 — Booked-slot buffer expansion

**Status: Accepted**

When checking candidates against existing BOOKED slots, each booked slot is expanded to its
occupied interval using **its own event type's** buffers (loaded by the orchestrator); if that
event type cannot be resolved, fall back to the generating event type's buffers. Rationale: a
booking's after-buffer is real host time and must protect against candidates from *other* event
types too.

## ADR-009 — Host-local generation range, UTC persistence

**Status: Accepted**

Default regeneration range:

```
[host-local today 00:00, host-local (today + SLOT_GENERATION_DAYS) 00:00)
SLOT_GENERATION_DAYS = 30
```

- "Today" is the host's calendar day in the **host timezone**, not UTC's.
- The range is converted to UTC at the persistence boundary; the DB stores UTC
  (`DateTime(timezone=True)`).
- Reconciliation touches only slots whose `start_at` falls in the resolved UTC range. Everything
  outside the range is untouched — no inserts, no updates, no deletes.

## ADR-010 — Sequential AsyncSession reads

**Status: Accepted**

The orchestrator loads availability, exceptions, event types, and booked slots **sequentially**
on the request's session. `AsyncSession` is not safe for concurrent use (the assignment calls
this out explicitly). Parallelism is deferred until profiling justifies separate sessions.

## ADR-011 — Conditional reconciliation writes

**Status: Accepted**

Every reconciliation `UPDATE` that changes a slot's status is conditional:

```
UPDATE slots SET status = :new
WHERE id = :id AND status IN ('AVAILABLE', 'BLOCKED')
```

A slot that became BOOKED between the orchestrator's read and its write is never overwritten.
Reconciliation outcomes:

| Situation (within range)                                   | Action                          |
| ---------------------------------------------------------- | ------------------------------- |
| candidate exists as AVAILABLE                              | leave (or update fields)        |
| candidate exists as BLOCKED                                | restore to AVAILABLE if valid   |
| candidate does not exist                                   | INSERT AVAILABLE                |
| candidate exists as BOOKED                                 | never touch                     |
| existing AVAILABLE/BLOCKED not in candidate set            | set BLOCKED                     |

## ADR-012 — ON CONFLICT DO NOTHING

**Status: Accepted**

Slot inserts use PostgreSQL `ON CONFLICT DO NOTHING` keyed on `(event_type_id, start_at, end_at)`
(unique constraint `uq_slot_event_type_start_end`). Two concurrent regenerations inserting the
same candidate: exactly one row; the loser no-ops instead of raising.

## ADR-013 — BOOKED preservation invariant

**Status: Accepted**

A slot that is BOOKED remains BOOKED through any regeneration, forever, unless the booking
workflow itself changes it. Regeneration never performs `BOOKED → AVAILABLE` or
`BOOKED → BLOCKED`. Enforced both by policy (reconciliation never targets BOOKED) and by
mechanism (conditional writes, ADR-011). The booking engine's DB backstop (partial unique index
on confirmed bookings) remains the ultimate guard.

## ADR-014 — BLOCKED provenance (current)

**Status: Accepted (Provisional until ADR-015 lands)**

There is currently no manual-block API; BLOCKED rows arise **only** from regeneration
reconciliation (ADR-011). Therefore "restore BLOCKED → AVAILABLE if valid" is safe: a BLOCKED row
is always a stale generation artifact.

## ADR-015 — Future manual-block provenance

**Status: Provisional (future phase)**

When manual blocking is added, BLOCKED rows must distinguish **system vs. manual** provenance
(e.g., a `blocked_reason`/`blocked_by` column or separate state), and regeneration must not
restore manual blocks. Recorded now so reconciliation does not silently undo explicit host blocks
later.

## ADR-016 — Temporal excluded from S1–S3

**Status: Accepted**

Slot generation/regeneration stays on the request path through S3. Temporal workflows
(`RegenerateHostSlotsWorkflow`, `SendBookingConfirmationEmailWorkflow`,
`CreateGoogleCalendarEventWorkflow`) are Phase S4 and are not mixed into the slot algorithm or
orchestrator in S1–S3.

## ADR-017 — Public listing contract (S3)

**Status: Accepted**

```
GET /api/public/users/{user_id}/event-types/{slug}/slots?from=&to=&timezone=
```

- `to − from <= 62 days`, otherwise `400`.
- Payload timestamps are UTC ISO-8601.
- The grouping key is the local calendar date in the requested timezone (e.g., `2026-08-10T23:30Z`
  groups under `2026-08-11` for Asia/Kolkata). The requested timezone is echoed in the response
  and defaults to the host's timezone.

## ADR-018 — Module layout

**Status: Accepted**

The pure engine and orchestrator stay co-located in `app/slots/`
(`slot_generation.py`, `service.py`, `repository.py`, `model.py`, `schema.py`). No
`app/services/` package is introduced — the existing per-domain layout is preserved.

## ADR-019 — Availability exceptions persistence (S2-A)

**Status: Accepted**

- New table `availability_exceptions` with `host_id` (FK users, CASCADE), `exception_date`
  (Date), `kind` (enum `BLOCK_FULL_DAY` / `BLOCK_PARTIAL` / `ADD_WINDOW`), nullable
  `start_time`/`end_time`, standard UUID + timestamp mixins.
- `kind` values follow the S1 pure engine's `ExceptionKind` terminology (same names and
  string values); the ORM enum parallels it deliberately — S1 is frozen, so the engine keeps
  its own enum and the orchestrator maps by value.
- Unique constraint `(host_id, exception_date, kind, start_time, end_time)`. Postgres treats
  NULLs as distinct, so full-day blocks (NULL times) are **not** deduped by the index alone;
  the service performs an explicit existence check (with `IS NULL` filters) before insert.
- CRUD lives under `app/availability/exceptions/` (subpackage of the availability domain) at
  `POST/GET /availability/exceptions`, `GET/PATCH/DELETE /availability/exceptions/{id}`, with
  host identity from the `x-user-id` header (consistent with Availability/Bookings; no auth
  system — per the booking-engine decision).
- The exceptions router is included in `app/main.py` **before** the availability router so the
  `GET /availability/exceptions` list route is not shadowed by
  `GET /availability/{availability_id}` (UUID parse → 422).

## ADR-020 — Exception validation semantics (S2-A)

**Status: Accepted**

- `BLOCK_PARTIAL` and `ADD_WINDOW` require `start_time` and `end_time` with `start < end`.
- `BLOCK_FULL_DAY` requires both times to be `None` (rejected explicitly, never silently
  ignored).
- The same rules apply on update (validated against the merged result).
- Create/update DTOs use `extra="forbid"` (matches the booking-engine strictness).
- Blocks override adds (S1 exception-ordering rule) — persistence stores raw rules; S1
  interprets them.

## ADR-021 — Regeneration contract (S2-B)

**Status: Accepted**

- Trigger: `POST /api/v1/slots/regenerate` with `x-user-id` host identity and optional
  `{from_date, to_date}`; calls `regenerate_host_slots(host_id, from_date, to_date)`.
- Range: host-local **inclusive** dates when supplied, expanded to
  `[from 00:00, to+1 00:00)` in the host's zone; default
  `[host-local today, host-local (today + SLOT_GENERATION_DAYS))` with
  `SLOT_GENERATION_DAYS = 30`. Boundaries convert to UTC at the persistence boundary; all DB
  queries, keying, and reconciliation operate on UTC.
- Collision set for generation = **BOOKED slots only**, expanded by their own event type's
  buffers (ADR-008); AVAILABLE/BLOCKED rows are reconciled by `(event_type_id, start_at,
  end_at)` key, never by collision.
- Reconciliation: insert AVAILABLE (`ON CONFLICT DO NOTHING`), restore BLOCKED → AVAILABLE,
  block AVAILABLE/BLOCKED not in the candidate set, never touch BOOKED; every status UPDATE is
  conditional on `status IN ('AVAILABLE','BLOCKED')` (ADR-011/012).
- Response: `SlotRegenerationResponse` with host_id, host-local from/to dates, timezone, and
  counts (generated / restored / blocked / kept / booked).
