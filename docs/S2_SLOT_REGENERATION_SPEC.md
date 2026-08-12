# Phase S2 — Slot Regeneration: Design Spec

**Status:** S2-A approved for implementation; S2-B specified, implementation to follow in its
own change. Complements `docs/DECISIONS.md` (ADRs 001–018, 019–021) and
`docs/S1_SLOT_GENERATION_SPEC.md`.

S2 answers: *"How do I get the data from PostgreSQL, feed it into S1, and safely reconcile
PostgreSQL with the generated result?"* It is split into two sub-phases and must not be
implemented as one giant change:

```text
S2-A  Availability exception persistence   (this change)
S2-B  Slot regeneration orchestration      (next change)
```

## Boundary invariants (carried over)

- `app/slots/slot_generation.py` = deterministic scheduling mathematics. **Frozen.**
- `slot_service` = orchestration only (load data, call engine, reconcile).
- Repository = data access only — **no interval mathematics in repositories**.
  `repository.find_exceptions(...)` yes; `repository.calculate_blocked_windows(...)` no.
- BOOKED slots are sacred: regeneration never performs `BOOKED → AVAILABLE/BLOCKED`
  (ADR-013), enforced by conditional writes (ADR-011) and `ON CONFLICT DO NOTHING`
  (ADR-012).
- Sequential reads on the request's `AsyncSession` (ADR-010) — no `asyncio.gather` on one
  session.

---

## S2-A — Availability exception persistence

### Table: `availability_exceptions`

| column          | type                          | notes                                            |
| --------------- | ----------------------------- | ------------------------------------------------ |
| `id`            | UUID PK                       |                                                  |
| `host_id`       | UUID FK `users.id` CASCADE    | indexed                                          |
| `exception_date`| `Date`                        | the affected host-local calendar date            |
| `kind`          | enum `availabilityexceptionkind` | `BLOCK_FULL_DAY`, `BLOCK_PARTIAL`, `ADD_WINDOW` |
| `start_time`    | `Time` nullable               | required for `BLOCK_PARTIAL` / `ADD_WINDOW`      |
| `end_time`      | `Time` nullable               | required for `BLOCK_PARTIAL` / `ADD_WINDOW`      |
| `created_at` / `updated_at` | `DateTime(timezone=True)` | standard mixin                                   |

- `UniqueConstraint(host_id, exception_date, kind, start_time, end_time)` — dedupes
  time-window exceptions. **Caveat:** Postgres treats NULLs as distinct by default, so two
  full-day blocks for the same host/date/kind are not deduped by the index alone; the service
  performs an explicit existence check (`IS NULL` filters) before insert. Documented in
  ADR-019.
- `Index(host_id, exception_date)` — serves the S2-B range query.

### Module layout

`app/availability/exceptions/` (subpackage under the existing availability domain):
`enums.py`, `model.py`, `schema.py`, `repository.py`, `service.py`, `router.py`.

The ORM enum `AvailabilityExceptionKind` intentionally parallels the pure engine's
`ExceptionKind` (same member names and string values). S1 is frozen, so the engine keeps its own
enum; the S2-B orchestrator maps between them trivially by value.

### Validation semantics (ADR-020)

- `BLOCK_PARTIAL` and `ADD_WINDOW`: `start_time` and `end_time` required, `start < end`.
- `BLOCK_FULL_DAY`: times must be `None` (explicit — no silent ignoring).
- Same rules on update, applied to the merged result.
- `extra="forbid"` on create/update DTOs (matches the booking-engine strictness).

### CRUD API (host identity via `x-user-id` header, consistent with Availability/Bookings)

```
POST   /availability/exceptions
GET    /availability/exceptions          (host-scoped)
GET    /availability/exceptions/{id}
PATCH  /availability/exceptions/{id}
DELETE /availability/exceptions/{id}     (204)
```

Errors: `404` unknown host / exception; `409` duplicate; `400` validation via the centralized
handlers. No per-route exception handling.

**Route-ordering note:** the `GET /availability/exceptions` list route can be shadowed by the
existing `GET /availability/{availability_id}` (UUID parse → 422). The exceptions router must be
included in `app/main.py` **before** the availability router; add a comment explaining why.

### Repository (data access only)

```
find_for_host_and_range(host_id, start_date, end_date)  # S2-B range query, date-inclusive
find_all_for_host(host_id)                              # ordered by exception_date, start_time
exists_for_host(host_id, kind, exception_date, start_time, end_time)
exists_for_host_excluding(host_id, kind, exception_date, start_time, end_time, exclude_id)
```

---

## S2-B — Slot regeneration orchestration

### Trigger

`POST /api/v1/slots/regenerate` with `x-user-id` header (host identity) and optional body
`{ "from_date": date?, "to_date": date? }`. Calls
`regenerate_host_slots(host_id, from_date=None, to_date=None)`.

### Range resolution (ADR-009 + ADR-021)

- Defaults: `from` = host-local **today** `00:00`; `to` = host-local
  `(today + SLOT_GENERATION_DAYS)` `00:00`, exclusive, with `SLOT_GENERATION_DAYS = 30`
  (module constant in `app/slots/service.py`).
- When `from_date`/`to_date` are supplied they are host-local **inclusive** calendar dates,
  internally expanded to `[from 00:00, to+1 00:00)` in the host's zone.
- Both boundaries are converted to **UTC instants** at the persistence boundary. The DB queries,
  the candidate keying, and the reconciliation all operate on UTC.
- "Today" is the host's calendar day in the **host timezone**, never `datetime.now(utc)` —
  the 30-day window is host calendar time, not 720 UTC hours (this matters around DST).
- Reconciliation touches only slots whose `start_at` falls in `[from_utc, to_utc)`. Everything
  outside is untouched.

### Data loading (sequential, one session)

```
1. host (UserRepository.find_by_id)            -> 404 if missing
2. availability rules (AvailabilityRepository.find_week_schedule)
3. exceptions (AvailabilityExceptionRepository.find_for_host_and_range)
4. event types (EventTypeRepository.find_by_host)
5. booked slots in range (SlotRepository.find_booked_by_host_in_range)
```

### ORM → pure mapping

The orchestrator maps ORM rows to the S1 dataclasses at the boundary; the engine never sees
SQLAlchemy objects:

```
EventType          -> EventTypeSpec(duration_minutes, buffer_before_minutes, buffer_after_minutes)
Availability       -> AvailabilityRule(day_of_week, start_time, end_time, is_available)
AvailabilityException -> ExceptionRule(kind=ExceptionKind[orm.kind.name], date, start_time, end_time)
Slot (BOOKED)      -> TimeWindow(occupied UTC interval)  # expanded per ADR-008
```

### Per-event-type generation

For each event type (its own duration/buffers):

```
candidates = engine.generate(event_type=spec, availability=rules,
                             exceptions=pure_exceptions, start_date, end_date,
                             timezone=host.timezone)
candidates = [c for c in candidates if c.start_at.astimezone(utc) > now_utc]  # no past slots
candidates = exclude_overlapping_booked(candidates, spec, booked_occupied_windows)
candidates_utc = [(event_type.id, c.start_at.astimezone(utc), c.end_at.astimezone(utc)) for c in candidates]
```

- **Booked-slot expansion (ADR-008):** each existing BOOKED slot is expanded by **its own
  event type's** buffers into a UTC occupied window; if that event type cannot be resolved,
  fall back to the generating event type's buffers.
- **Collision set = BOOKED slots only.** Existing AVAILABLE/BLOCKED slots are reconciled by
  key, not by collision — they cannot collide with candidates because equal
  `(event_type_id, start_at, end_at)` rows are the same candidate.
- **Past-slot filter lives in the orchestrator** (the engine is clockless, by design).

### Reconciliation (ADR-011, ADR-012)

Keyed by `(event_type_id, start_at, end_at)` (the existing unique constraint
`uq_slot_event_type_start_end`), within the UTC range:

| generated candidate | existing row        | action                                    |
| ------------------- | ------------------- | ----------------------------------------- |
| yes                 | — (missing)         | `INSERT ... ON CONFLICT DO NOTHING`       |
| yes                 | AVAILABLE           | keep (no-op)                              |
| yes                 | BLOCKED             | `UPDATE ... SET status='AVAILABLE' WHERE status IN ('AVAILABLE','BLOCKED')` |
| yes                 | BOOKED              | **never touch**                           |
| no                  | AVAILABLE/BLOCKED   | `UPDATE ... SET status='BLOCKED' WHERE status IN ('AVAILABLE','BLOCKED')` |
| no                  | BOOKED              | **never touch**                           |

Every status-changing `UPDATE` is conditional on `status IN ('AVAILABLE','BLOCKED')`; every
insert uses `ON CONFLICT DO NOTHING`.

### Race analysis (regeneration vs. booking)

Booking locks the slot row with `SELECT ... FOR UPDATE` inside its transaction; regeneration
does not lock, but its writes are conditional:

1. **Regen reads AVAILABLE, booking commits BOOKED first** → regen's conditional UPDATE matches
   0 rows → preserved. ✓
2. **Regen reads AVAILABLE, booking in flight** → regen's UPDATE blocks on the row lock until
   the booking commits; then the WHERE clause sees BOOKED → 0 rows. ✓
3. **Regen inserts a new slot** → bookings cannot target a slot that does not exist (booking
   FK requires an existing `slot_id`), and a booking that starts after the insert simply sees
   the new AVAILABLE row. ✓
4. **Two concurrent regenerations** → same deterministic candidate set; concurrent inserts hit
   the unique constraint and `ON CONFLICT DO NOTHING` resolves the race; conditional updates are
   idempotent. Final state identical. ✓

The DB backstop for the booking invariant itself (partial unique index on confirmed bookings)
is unchanged.

### Response contract (ADR-021)

`SlotRegenerationResponse`:

```
host_id: UUID
from_date: date        # host-local inclusive
to_date: date          # host-local inclusive (default: today + SLOT_GENERATION_DAYS - 1)
timezone: str
generated_count: int   # inserted as AVAILABLE
restored_count: int    # BLOCKED -> AVAILABLE
blocked_count: int     # AVAILABLE/BLOCKED -> BLOCKED
kept_count: int        # already AVAILABLE, unchanged
booked_count: int      # BOOKED, untouched
```

---

## S2 test plan

### S2-A (this change)

- **Service (mocked repos, runnable without Postgres):** create success; host missing → 404;
  duplicate → 409; list delegates; get/update/delete; update duplicate excluding self → 409;
  delete missing → 404; logging.
- **API (real app + Postgres, follows existing `tests/e2e` pattern):** 201 shape; duplicate
  409; invalid kind-without-times 422; full-day-with-times 422; extra field 422; host-scoped
  list; 404s; PATCH; DELETE 204. *(Written in this change; run when Postgres is available.)*

### S2-B (next change)

- **Service/unit:** default range resolution; explicit range; host timezone; sequential load
  calls; ORM→pure mapping; per-event-type generation; past-slot filter; booked expansion;
  collision exclusion; reconciliation branches (new/keep/restore/block); BOOKED preservation;
  idempotency (run twice → same state).
- **Real Postgres integration:** regenerate twice → same slot set, no duplicates; regeneration
  + booking race → BOOKED never becomes AVAILABLE/BLOCKED; date-range filtering; unique
  constraint + `ON CONFLICT DO NOTHING`.
