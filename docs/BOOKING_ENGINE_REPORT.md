# Booking Engine — QA Report (Assignment-Compliance Audit)

## BOOKING ENGINE STATUS: COMPLETE

## Scope
Make the Booking Engine (`app/bookings/*` + supporting infra) production-grade, tested, and
aligned with the assignment contract (Part 2 §10 Bookings). The mandatory critical invariant:

> A single slot can NEVER yield two confirmed bookings, even under concurrent requests.

## Assignment contract (implemented)
- **POST /bookings request:** `slotId`, `inviteeEmail`, `inviteeName`, `inviteeNotes`.
  No `attendee_id` — invitees are free-form contact data, not registered users.
- **Booking persistence fields**: `hostId`, `eventTypeId`, `slotId`, `inviteeEmail`,
  `inviteeName`, `inviteeNotes`, `status`, `meetLink`, `calendarEventId`, `cancelledAt`.
- **GET /bookings** (host-scoped via `x-user-id` header) returns bookings enriched with
  `startAt`, `endAt`, and `eventType` (id/title/slug/duration).
- **Status codes**: `404` Slot not found; `400` Slot is not available; `400` Slot has
  already started; `400` host self-booking (by email match).

## Concurrency mechanism (preserved + backstop)
- **Pessimistic (routed)**: `SELECT ... FOR UPDATE` via
  `BookingRepository.find_slot_for_update` inside the booking transaction.
- **Optimistic (exists, TESTED but NOT routed)**: `BookingRepository.try_occupy_slot` —
  conditional `UPDATE slots SET status='BOOKED' WHERE id=:id AND status='AVAILABLE'`,
  returning True only when a row flipped.
- **DB backstop**: partial unique index `uq_bookings_confirmed_slot (slot_id)
  WHERE status='confirmed'` — a second CONFIRMED booking for a slot raises IntegrityError
  even if a race slips past the lock.

## Defects found and fixed
1. **Request DTO violated the assignment** — `attendee_id` dropped in favor of
   `invitee_email`/`invitee_name`/`invitee_notes`; `extra="forbid"` retained.
2. **Booking model lacked contract fields** — added `event_type_id` (derived from slot),
   `invitee_email`, `invitee_name`, `invitee_notes`, `meet_link`, `calendar_event_id`,
   `cancelled_at`; removed `attendee_id` FK and its user-linking.
3. **HTTP status codes** — unavailable/started/self bookings changed from 409 to **400**
   per the assignment contract; 404 for missing slot retained.
4. **Self-booking guard updated** — now compares inviteeEmail (case-insensitive) against
   the slot owner's registered email, since there is no attendee user anymore.
5. **Slot-already-started check added** — rejects bookings whose start time has passed.
6. **GET /bookings added** — host-scoped listing via `x-user-id` header, richer response.
7. **Optimistic strategy implemented + tested but NOT routed** — available in the
   repository with its own integration tests.

## Test coverage (all in `tests/e2e/`)
| File | Tests | Level | Key assertions |
|---|---|---|---|
| `test_bookings_service.py` | 13 | Service (mocked repo) | success, host/event_type derived from slot, slot-not-found 404, started/booked/blocked 400, email self-booking 400, IntegrityError->400, logging, list delegation |
| `test_bookings_repository.py` | 15 | Repository (real Postgres) | CRUD, confirmed filter, pagination, `FOR UPDATE` compile, optimistic occupy flips AVAILABLE only, DB IntegrityError double-booking (unique index) |
| `test_bookings_api.py` | 20 | API (real app + DB) | 201 + enriched shape, persisted state, 400 validations (missing/invalid/null/extra fields), 404 contract, 400 booked slot, 400 self-booking, GET listing + scoping, centralized error envelope, safe 500 |
| `test_bookings_concurrency.py` | 3 | Real concurrency + rollback | two-invitee same slot, same-invitee duplicate, rollback leaves slot AVAILABLE |

## Mandatory criteria — all GREEN
- [x] Concurrency invariant proven on real Postgres: two parallel bookings same slot →
      statuses `[201, 400]`; exactly one booking row, one CONFIRMED; slot ends `BOOKED`;
      same-invitee duplicate likewise one winner.
- [x] Pessimistic strategy exists **and is routed** (`find_slot_for_update` used in service).
- [x] Optimistic strategy exists (conditional `UPDATE ... WHERE status='AVAILABLE'`),
      is tested, and is **NOT** routed.
- [x] Migration applied and clean on dev + test DBs at head `b2f7e6d5c4a3`;
      fresh-DB `upgrade head` works through all 7 revisions; downgrade/upgrade round-trip
      verified; `alembic check` clean on all three DBs.
- [x] Rollback/transaction test: failed booking leaves slot AVAILABLE, bookings count 0.
- [x] No external network calls or Temporal workflow starts before the transaction commits.
- [x] No auth system introduced (host identity remains `x-user-id`).
- [x] No debug code (`print`/`breakpoint`/`pdb`) added.
- [x] No secrets/credentials committed.

## Framework edge case (documented, unchanged)
Starlette's `ServerErrorMiddleware` always re-raises after sending a 500 (by design). Under
`httpx.ASGITransport` the raised exception surfaces unless `raise_app_exceptions=False`.
`test_unexpected_internal_error_returns_500_safely` uses that flag to assert the
`{success:false}` 500 body without a production change.

## Final suite
`pytest -q` → **157 passed, 6 skipped, 0 failed.**
`alembic check` → clean on dev, test, and fresh-upgraded DBs.

## Conclusion
Booking kernel (Router -> Service -> Repository -> PostgreSQL) and assignment contract are
production-grade and exhaustively verified. A single slot can never yield two confirmed
bookings. **BOOKING PHASE CLOSED — READY FOR PUBLIC SLOT LISTING / TEMPORAL PHASE.**