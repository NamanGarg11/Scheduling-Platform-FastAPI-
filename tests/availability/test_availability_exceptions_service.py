"""Service-layer tests for availability exceptions (mocked repositories, no DB)."""

from datetime import date, time
from unittest.mock import AsyncMock
from uuid import uuid4

from app.availability.exceptions.enums import AvailabilityExceptionKind
from app.availability.exceptions.model import AvailabilityException
from app.availability.exceptions.repository import AvailabilityExceptionRepository
from app.availability.exceptions.schema import (
    CreateAvailabilityExceptionRequest,
    UpdateAvailabilityExceptionRequest,
)
from app.availability.exceptions.service import AvailabilityExceptionService
from app.core.exceptions.base import ConflictException, NotFoundException
from app.users.repository import UserRepository


def make_exception(
    *,
    host_id: object | None = None,
    kind: AvailabilityExceptionKind = AvailabilityExceptionKind.BLOCK_PARTIAL,
    exception_date: date = date(2026, 8, 17),
    start_time: time | None = time(12, 0),
    end_time: time | None = time(14, 0),
) -> AvailabilityException:
    return AvailabilityException(
        id=uuid4(),
        host_id=host_id or uuid4(),
        exception_date=exception_date,
        kind=kind,
        start_time=start_time,
        end_time=end_time,
    )


def make_create_request(
    kind: AvailabilityExceptionKind = AvailabilityExceptionKind.BLOCK_PARTIAL,
    exception_date: date = date(2026, 8, 17),
    start_time: time | None = time(12, 0),
    end_time: time | None = time(14, 0),
) -> CreateAvailabilityExceptionRequest:
    return CreateAvailabilityExceptionRequest(
        kind=kind,
        date=exception_date,
        start_time=start_time,
        end_time=end_time,
    )


def build_service(
    *,
    host_exists: bool = True,
    duplicate: bool = False,
    duplicate_excluding: bool = False,
    exception: AvailabilityException | None = None,
) -> tuple[AvailabilityExceptionService, AsyncMock, AsyncMock]:
    repo = AsyncMock(spec=AvailabilityExceptionRepository)
    repo.exists_for_host = AsyncMock(return_value=duplicate)
    repo.exists_for_host_excluding = AsyncMock(return_value=duplicate_excluding)
    repo.find_by_id = AsyncMock(return_value=exception)
    repo.find_all_for_host = AsyncMock(return_value=[exception] if exception else [])

    async def save(entity):
        return entity

    repo.save = AsyncMock(side_effect=save)

    user_repo = AsyncMock(spec=UserRepository)
    user_repo.find_by_id = AsyncMock(
        return_value=object() if host_exists else None,
    )

    service = AvailabilityExceptionService(
        repository=repo,
        user_repository=user_repo,
    )
    return service, repo, user_repo


async def test_create_exception_success():
    service, repo, _ = build_service()
    host_id = uuid4()
    request = make_create_request()

    result = await service.create_exception(host_id, request)

    assert result.host_id == host_id
    assert result.exception_date == request.exception_date
    assert result.kind == request.kind
    assert result.start_time == request.start_time
    assert result.end_time == request.end_time
    repo.save.assert_awaited()


async def test_create_exception_full_day():
    service, _, _ = build_service()
    request = CreateAvailabilityExceptionRequest(
        kind=AvailabilityExceptionKind.BLOCK_FULL_DAY,
        date=date(2026, 8, 17),
    )

    result = await service.create_exception(uuid4(), request)

    assert result.kind == AvailabilityExceptionKind.BLOCK_FULL_DAY
    assert result.start_time is None
    assert result.end_time is None


async def test_create_exception_host_missing_raises_404():
    service, _, _ = build_service(host_exists=False)

    try:
        await service.create_exception(uuid4(), make_create_request())
        raise AssertionError("expected NotFoundException")
    except NotFoundException as exc:
        assert exc.status_code == 404
        assert "host" in exc.message


async def test_create_exception_duplicate_raises_409():
    service, _, _ = build_service(duplicate=True)

    try:
        await service.create_exception(uuid4(), make_create_request())
        raise AssertionError("expected ConflictException")
    except ConflictException as exc:
        assert exc.status_code == 409


async def test_list_exceptions_delegates_to_host():
    exception = make_exception()
    service, repo, _ = build_service(exception=exception)
    host_id = uuid4()

    result = await service.list_exceptions(host_id)

    assert len(result) == 1
    repo.find_all_for_host.assert_awaited_with(host_id)


async def test_get_exception_success():
    exception = make_exception()
    service, _, _ = build_service(exception=exception)

    result = await service.get_exception(exception.id)

    assert result.id == exception.id


async def test_get_exception_missing_raises_404():
    service, _, _ = build_service(exception=None)

    try:
        await service.get_exception(uuid4())
        raise AssertionError("expected NotFoundException")
    except NotFoundException as exc:
        assert exc.status_code == 404


async def test_update_exception_success():
    exception = make_exception()
    service, repo, _ = build_service(exception=exception)
    new_date = date(2026, 8, 20)

    result = await service.update_exception(
        exception.id,
        UpdateAvailabilityExceptionRequest(date=new_date),
    )

    assert result.exception_date == new_date
    repo.exists_for_host_excluding.assert_awaited()
    repo.save.assert_awaited()


async def test_update_exception_duplicate_raises_409():
    exception = make_exception()
    service, _, _ = build_service(
        exception=exception,
        duplicate_excluding=True,
    )

    try:
        await service.update_exception(
            exception.id,
            UpdateAvailabilityExceptionRequest(date=date(2026, 8, 20)),
        )
        raise AssertionError("expected ConflictException")
    except ConflictException as exc:
        assert exc.status_code == 409


async def test_update_exception_no_op_skips_duplicate_check():
    exception = make_exception()
    service, repo, _ = build_service(exception=exception)

    await service.update_exception(
        exception.id,
        UpdateAvailabilityExceptionRequest(),
    )

    repo.exists_for_host_excluding.assert_not_awaited()


async def test_delete_exception_success():
    exception = make_exception()
    service, repo, _ = build_service(exception=exception)

    await service.delete_exception(exception.id)

    repo.delete.assert_awaited()


async def test_delete_exception_missing_raises_404():
    service, _, _ = build_service(exception=None)

    try:
        await service.delete_exception(uuid4())
        raise AssertionError("expected NotFoundException")
    except NotFoundException as exc:
        assert exc.status_code == 404
