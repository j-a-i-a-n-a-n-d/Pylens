from __future__ import annotations

from pylens.dpi import DpiBackend, DpiInfo


class GenericDpiBackend(DpiBackend):
    """Generic DPI backend for unknown platforms."""

    def set_dpi_awareness(self) -> None:
        pass

    def get_system_dpi(self) -> int:
        return 96

    def get_screen_dpi(self, screen_index: int = 0) -> DpiInfo:
        return DpiInfo(96, 96, 1.0)

    def physical_to_logical(self, value: float, screen_index: int = 0) -> float:
        return value

    def logical_to_physical(self, value: float, screen_index: int = 0) -> float:
        return value