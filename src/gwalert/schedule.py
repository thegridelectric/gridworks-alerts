"""Parse on-call schedule rows from a Google Sheet."""

from typing import TypedDict


class ScheduleEntry(TypedDict):
    day: int
    hour_start: int
    names: list[str]


Schedule = dict[int, dict[int, list[str]]]
Contacts = dict[str, str]

DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
DAY_TO_INDEX = {day: index for index, day in enumerate(DAYS)}


def parse_hour_start(value: str) -> int:
    """Convert a cell like '11:00' to hour 11."""
    hour_part = value.strip().split(":", maxsplit=1)[0]
    return int(hour_part)


def parse_names(value: str) -> list[str]:
    """Split a cell like 'George, Jessica' into ['George', 'Jessica']."""
    if not value.strip():
        return []
    return [name.strip() for name in value.split(",") if name.strip()]


def parse_schedule_rows(rows: list[list[str]]) -> Schedule:
    """Build day -> hour_start -> names from a worksheet grid."""
    if not rows:
        return {}

    header = rows[0]
    day_columns: list[tuple[int, int]] = []
    for col_idx, label in enumerate(header[1:], start=1):
        day = label.strip().lower()
        if day in DAY_TO_INDEX:
            day_columns.append((col_idx, DAY_TO_INDEX[day]))

    schedule: Schedule = {day_index: {} for _, day_index in day_columns}

    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        hour_start = parse_hour_start(row[0])
        for col_idx, day_index in day_columns:
            cell = row[col_idx] if col_idx < len(row) else ""
            schedule[day_index][hour_start] = parse_names(cell)

    return schedule


def parse_contacts_rows(rows: list[list[str]]) -> Contacts:
    """Build name -> Telegram chat ID from a contacts worksheet."""
    if not rows:
        return {}

    header = [label.strip().lower() for label in rows[0]]
    try:
        name_idx = header.index("name")
        chat_id_idx = header.index("telegram chat id")
    except ValueError:
        return {}

    contacts: Contacts = {}
    for row in rows[1:]:
        if name_idx >= len(row) or not row[name_idx].strip():
            continue
        name = row[name_idx].strip()
        chat_id = row[chat_id_idx].strip() if chat_id_idx < len(row) else ""
        if chat_id:
            contacts[name] = chat_id

    return contacts


def schedule_to_entries(schedule: Schedule) -> list[ScheduleEntry]:
    """Flatten a schedule into sorted entries for easier inspection."""
    entries: list[ScheduleEntry] = []
    for day_index in range(len(DAYS)):
        if day_index not in schedule:
            continue
        for hour_start in sorted(schedule[day_index]):
            entries.append(
                {
                    "day": day_index,
                    "hour_start": hour_start,
                    "names": schedule[day_index][hour_start],
                }
            )
    return entries
