# Phase S1 — Pure Slot Generation Engine: Design Spec

**Status:** Approved for implementation. Complements `docs/DECISIONS.md` (ADRs 001–007, 016,
018).

## Scope

`app/slots/slot_generation.py` is an **evolution/refinement** of the existing pure engine, not a
rewrite. It contains **only interval mathematics**: inputs in, calculated intervals out.

### Non-goals (S1)

- No SQLAlchemy, PostgreSQL, `AsyncSession`, repositories, FastAPI, HTTP, external APIs.
- No `datetime.now()` / `utcnow()` — the engine is time-agnostic; it takes explicit dates.
- No exceptions **table/model** (that is S2; S1 models exceptions as pure data).
- No regeneration/reconciliation (S2), no public listing (S3), no Temporal (S4).
- No change to the **stepping semantics** — ADR-003, pinned by the existing test.
- No changes to `service.py`, repositories, migrations, or the booking engine. The engine's
  `generate()` remains **duck-typed** so the existing orchestrator can keep passing ORM models
  unchanged (S1 introduces pure dataclasses as the canonical types; the orchestrator maps
  ORM → pure in S2).

### Allowed imports

`datetime` / `date` / `time`, `zoneinfo`, `dataclasses`, `enum`, `typing` — plus the pure enums
`app.availability.enums.DayOfWeek` (and `app.event_types.enums` if needed). Importing ORM models,
repositories, or settings is a violation. Enforced by `tests/slots/test_import_purity.py`.

## Data structures (pure)

```python
@dataclass(frozen=True, slots=True)
class TimeWindow:          # half-open [start, end); aware datetimes, host-local zone
    start: datetime
    end: datetime

@dataclass(frozen=True, slots=True)
class EventTypeSpec:       # pure projection of EventType
    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int

@dataclass(frozen=True, slots=True)
class AvailabilityRule:    # pure projection of an Availability row
    day_of_week: DayOfWeek
    start_time: time
    end_time: time
    is_available: bool

class ExceptionKind(Enum):
    BLOCK_FULL_DAY
    BLOCK_PARTIAL
    ADD_WINDOW

@dataclass(frozen=True, slots=True)
class ExceptionRule:
    kind: ExceptionKind
    date: date
    start_time: time | None = None   # required for BLOCK_PARTIAL / ADD_WINDOW
    end_time: time | None = None

@dataclass(frozen=True, slots=True)
class SlotCandidate:       # the meeting interval, host-local zone
    start_at: datetime
    end_at: datetime
```

The engine emits aware datetimes in the **host's local zone** (ADR-007 — the existing stepping
test asserts local wall-clock hours). UTC conversion is the orchestrator's job at the persistence
boundary (ADR-009). Collision intervals (`occupied`) are returned in **UTC instants** — the
collision domain is real time, not wall clock.

## Primitive functions

### `parse_time_on_date(d: date, t: time, tz: ZoneInfo, *, fold: int = 0) -> datetime`

`datetime.combine(d, t.replace(fold=fold), tzinfo=tz)` — `combine` does not accept `fold`, so it
is set on the `time` argument. This is the single place DST resolution happens (ADRs 005–006):

- Nonexistent local time (spring-forward gap) → resolves to the pre-gap offset, i.e. the UTC
  instant the wall clock would have reached absent the jump (wall time shifts forward by the gap).
- Ambiguous local time (autumn-back) → `fold=0` picks the first occurrence (DST).

### `windows_for_weekday_rule(rule: AvailabilityRule, start_date: date, end_date: date, tz: ZoneInfo) -> list[TimeWindow]`

Expands a weekly rule into concrete windows for each date in `[start_date, end_date]` where
`rule.day_of_week` matches **and** `rule.is_available` is true. Each window is resolved via
`parse_time_on_date`. Windows with `end <= start` are dropped.

### `merge_windows(windows: list[TimeWindow]) -> list[TimeWindow]`

Sorts by start; merges when `next.start <= current.end` (touching merges, ADR-002). Output:
sorted, non-overlapping, half-open.

### `subtract_windows(windows: list[TimeWindow], blocked: list[TimeWindow]) -> list[TimeWindow]`

Removes blocked intervals (half-open overlap) from windows; result is the sorted remainder.
`blocked` is assumed already merged. A full containment leaves an empty remainder (dropped).

### `apply_exceptions(windows: list[TimeWindow], exceptions: list[ExceptionRule], tz: ZoneInfo) -> list[TimeWindow]`**A block always overrides an added window (blocks win)** — implemented by applying
`ADD_WINDOW` first, then blocks, so an added window inside a blocked span is removed by the
block (input order is irrelevant):

1. `ADD_WINDOW` — union the added window(s); merge.
2. `BLOCK_FULL_DAY` — drop all windows whose local calendar date is that date (including
   added windows on that date).
3. `BLOCK_PARTIAL` — subtract `[t0, t1)` resolved on that date (including added windows
   inside the span).

Exceptions **override** availability rules. An `ADD_WINDOW` on a date with no base
availability creates availability; a `BLOCK_*` on an empty date is a no-op. Exceptions on
dates outside the requested range are harmless no-ops (their window is outside the merged
set).

### `split_into_slots(window: TimeWindow, spec: EventTypeSpec) -> list[SlotCandidate]`

Implements ADR-003 exactly, with **UTC-anchored stepping** (ADR-003 amendment):

```
utc_start = window.start.astimezone(utc)
utc_end   = window.end.astimezone(utc)
occupied  = spec.buffer_before_minutes + spec.duration_minutes + spec.buffer_after_minutes
cursor    = utc_start
while cursor + occupied <= utc_end:            # touching at window end is allowed
    emit SlotCandidate(cursor + before, cursor + before + duration)
    cursor += occupied
# each candidate converted back to the window's local zone before returning
```

#### Stepping anchor (rationale, verified empirically)

Wall-clock stepping across a spring-forward gap folds the cursor back onto earlier UTC
intervals. For a `00:30–03:00` London window on 2026-03-29 (D=30, no buffers), wall-clock
stepping yields 5 candidates of which only 4 are distinct UTC intervals and one pair is
out-of-order — the `02:00` wall cursor resolves to `01:00 UTC`, *before* the previous candidate
that ended at `01:30 UTC`. Resolving each cursor through the DST resolver does not fix this,
because the fold is caused by the cursor progression, not the resolution.

UTC-anchored stepping yields 3 monotonic, non-duplicated candidates
(`00:30 / 01:00 / 01:30 UTC`), displayed locally as `00:30 / 02:00 / 02:30 BST` — jumping over
the gap exactly as the wall clock does. On non-DST days the two approaches are identical, so the
pinned 4-slot test is byte-for-byte unchanged.

### Collision primitives

`occupied(candidate: SlotCandidate, spec: EventTypeSpec) -> TimeWindow` — the candidate's
collision interval `[start − before, end + after)` (ADR-004), computed as **UTC instants**:
`candidate.start_at.astimezone(utc) − before` … `+ after`. Wall-clock subtraction would be off by
the offset delta around DST transitions, so the collision domain is real time.

`overlaps_booked(candidate: SlotCandidate, spec: EventTypeSpec, booked: TimeWindow) -> bool` —
half-open overlap between the candidate's occupied interval and a booked interval (ADR-008: the
booked interval passed in is already expanded by its own event type's buffers). Touching is
allowed.

`exclude_overlapping_booked(candidates: list[SlotCandidate], spec: EventTypeSpec, booked_windows: list[TimeWindow]) -> list[SlotCandidate]` — filters candidates whose occupied interval
overlaps any booked window. The S2 orchestrator uses this to keep generated slots clear of
existing bookings.

## Top-level composition

`generate(*, event_type: EventTypeSpec, availability: list[AvailabilityRule], exceptions: list[ExceptionRule] | None, start_date: date, end_date: date, timezone: str) -> list[SlotCandidate]`

```
windows = concat(windows_for_weekday_rule(rule, ...) for rule in availability)
windows = apply_exceptions(merge_windows(windows), exceptions or [], tz)
windows = merge_windows(windows)
return flatten(split_into_slots(w, event_type) for w in windows)
```

With no exceptions and no DST edges, this is behaviorally identical to the current engine —
**existing tests are the contract** and must stay green with identical assertions.

## Edge cases (normative)

- **Zero-length / negative windows** (`end <= start`) → dropped.
- **Candidate touching window end** — the loop's `<=` allows the last candidate whose occupied
  interval ends exactly at `window.end` (e.g. `11:50 + 10min buffer = 12:00` in the pinned test).
- **Candidate touching a booking** (occupied ends exactly at booking's occupied start) → allowed.
- **Weekend/absent rule** → no windows that day.
- **`is_available=False`** → rule contributes nothing (current behavior).
- **Windows spanning a DST transition** → endpoints resolved independently (ADRs 005–006) and the
  cursor stepped in UTC (ADR-003 amendment); the elapsed wall-clock duration may differ from the
  UTC span. Expected, tested.
- **Past slots** → out of scope for the engine (no clock); the orchestrator (S2) filters.

## Test matrix (`tests/slots/test_generation.py`)

| Area | Cases |
| --- | --- |
| Stepping (preserved verbatim) | 09:00–12:00 / 30 / 5 / 10 → `09:05, 09:50, 10:35, 11:20` |
| Stepping variants | no buffers; buffer-before only; buffer-after only; 120-min window; 480-min window; 1-min duration |
| Weekday expansion | single rule across a multi-day range; weekend gap; `is_available=False`; multiple rules per day |
| Merge | overlapping windows; touching windows (merge); disjoint windows (keep); unsorted input |
| Subtract | partial block (middle); full containment; edge-touching block (no-op); empty remainder |
| Exceptions | full-day block; partial block; added window on empty day; block-then-add ordering; exception on date outside range (ignored) |
| DST spring (2026-03-29 London) | nonexistent `01:30` resolves to pre-gap offset; window crossing the gap → no phantom, no duplicate, monotonic UTC, correct count (real hours ÷ occupied) |
| DST autumn (2026-10-25 London) | ambiguous `01:30` → `fold=0` (BST); `fold=1` → distinct UTC instant; window spanning the fold → both occurrences present as distinct UTC instants |
| Timezone conversion | Asia/Kolkata window → correct UTC instants and local hours |
| Buffers | occupied vs meeting interval; first candidate offset by buffer-before |
| Booked overlap | candidate overlapping booking → rejected; touching booking → allowed; overlap with expanded booked buffers |
| Boundaries | zero-length window; window end == start + occupied (allowed); candidate exactly at booking start (allowed) |
| Purity | `tests/slots/test_import_purity.py`: no `sqlalchemy`/`fastapi`/`app.core`/`.model`/`.repository` imports; no clock access |

Past-slot filtering and UTC persistence are **S2** tests, not S1.

## Acceptance criteria

1. `pytest tests/slots -q` green.
2. The pinned stepping test keeps every existing assertion, only its fixture construction changes
   from ORM models to `EventTypeSpec` / `AvailabilityRule` (pure types — see "Data structures").
3. `slot_generation.py` imports only stdlib + `app.availability.enums` (+ `app.event_types.enums`
   if needed); no `sqlalchemy` / `fastapi` / `app.core` / `app.*.model` imports (guarded by test).
4. `app/slots/service.py`, repositories, migrations, and the booking engine are untouched.
5. No new ruff findings in the touched files beyond the repo's documented intentional patterns.
