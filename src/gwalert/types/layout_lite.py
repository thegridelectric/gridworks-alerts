from gwalert.types._aliases import GwMessage


class LayoutLite(GwMessage):
    critical_zone_list: list[str] = []
    system_mode: str | None = None
