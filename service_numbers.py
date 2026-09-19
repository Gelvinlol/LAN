"""Canonical service-number timetable for the unit's operational 24-hour day."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
from typing import Final


ServiceNumber = int


@dataclass(frozen=True)
class ServiceShift:
    start: str
    end: str

    @property
    def label(self):
        return f"{self.start} - {self.end}"


SERVICE_NUMBER_SHIFTS: Final[dict[ServiceNumber, tuple[ServiceShift, ...]]] = {
    1: (
        ServiceShift("15:00", "18:00"),
        ServiceShift("00:00", "02:00"),
        ServiceShift("06:00", "09:00"),
    ),
    2: (
        ServiceShift("18:00", "21:00"),
        ServiceShift("02:00", "04:00"),
        ServiceShift("09:00", "12:00"),
    ),
    3: (
        ServiceShift("21:00", "00:00"),
        ServiceShift("04:00", "06:00"),
        ServiceShift("12:00", "15:00"),
    ),
}

# Minute ranges are start-inclusive and end-exclusive. Midnight is minute zero.
_CHRONOLOGICAL_RANGES: Final[tuple[tuple[int, int, ServiceNumber], ...]] = (
    (0, 120, 1),
    (120, 240, 2),
    (240, 360, 3),
    (360, 540, 1),
    (540, 720, 2),
    (720, 900, 3),
    (900, 1080, 1),
    (1080, 1260, 2),
    (1260, 1440, 3),
)


def _validate_service_number(service_number: ServiceNumber) -> ServiceNumber:
    try:
        normalized = int(service_number)
    except (TypeError, ValueError) as exc:
        raise ValueError("Το νούμερο υπηρεσίας πρέπει να είναι 1, 2 ή 3.") from exc
    if normalized not in SERVICE_NUMBER_SHIFTS:
        raise ValueError("Το νούμερο υπηρεσίας πρέπει να είναι 1, 2 ή 3.")
    return normalized


def get_service_number_shifts(service_number: ServiceNumber) -> tuple[ServiceShift, ...]:
    """Return all three shifts inherited by a service number."""
    return SERVICE_NUMBER_SHIFTS[_validate_service_number(service_number)]


def get_service_number_at(value: str | time | datetime) -> ServiceNumber:
    """Return which service number is on duty at a wall-clock time."""
    if isinstance(value, datetime):
        clock_time = value.time()
    elif isinstance(value, time):
        clock_time = value
    elif isinstance(value, str):
        try:
            clock_time = datetime.strptime(value, "%H:%M").time()
        except ValueError as exc:
            raise ValueError("Η ώρα πρέπει να έχει μορφή HH:MM.") from exc
    else:
        raise TypeError("Η ώρα πρέπει να είναι κείμενο, time ή datetime.")

    minute_of_day = clock_time.hour * 60 + clock_time.minute
    for start_minute, end_minute, service_number in _CHRONOLOGICAL_RANGES:
        if start_minute <= minute_of_day < end_minute:
            return service_number
    raise ValueError("Δεν βρέθηκε νούμερο υπηρεσίας για αυτή την ώρα.")


def get_service_shift_occurrences(
    service_date: date, service_number: ServiceNumber
) -> tuple[tuple[datetime, datetime], ...]:
    """Resolve a number's shifts on an operational day running 15:00–15:00.

    ``service_date`` is the calendar date on which the operational duty starts.
    Shifts from 00:00 through 15:00 therefore occur on the following date.
    """
    return get_shift_occurrences_for_shifts(
        service_date, get_service_number_shifts(service_number)
    )


def get_shift_occurrences_for_shifts(
    service_date: date, shifts
) -> tuple[tuple[datetime, datetime], ...]:
    """Resolve arbitrary configured shifts within the 15:00–15:00 duty day."""
    occurrences = []
    for shift in shifts:
        start_clock = datetime.strptime(shift.start, "%H:%M").time()
        end_clock = datetime.strptime(shift.end, "%H:%M").time()
        start_day = service_date if start_clock.hour >= 15 else service_date + timedelta(days=1)
        start_at = datetime.combine(start_day, start_clock)

        if shift.end == "00:00":
            end_day = service_date + timedelta(days=1)
        else:
            end_day = start_day
        end_at = datetime.combine(end_day, end_clock)
        if end_at <= start_at:
            end_at += timedelta(days=1)
        occurrences.append((start_at, end_at))
    return tuple(occurrences)


def serialize_service_shifts(shifts) -> str:
    """Store a stable copy of configured times on a duty assignment."""
    return json.dumps(
        [{"start": shift.start, "end": shift.end} for shift in shifts],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def deserialize_service_shifts(payload: str | None) -> tuple[ServiceShift, ...]:
    if not payload:
        return ()
    try:
        values = json.loads(payload)
        return tuple(ServiceShift(item["start"], item["end"]) for item in values)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return ()


def format_service_number_shifts(service_number: ServiceNumber) -> str:
    return " · ".join(shift.label for shift in get_service_number_shifts(service_number))
