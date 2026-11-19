"""图种注册表。新增图种时在此导入并注册即可。"""
from __future__ import annotations

from .architecture import ArchitectureDiagram
from .gantt import GanttDiagram
from .swimlane import SwimlaneDiagram

REGISTRY: dict[str, type] = {
    "architecture": ArchitectureDiagram,
    "gantt": GanttDiagram,
    "swimlane": SwimlaneDiagram,
}

DEFAULT_DIAGRAM = "architecture"


def get_renderer(diagram_type: str):
    if diagram_type not in REGISTRY:
        avail = ", ".join(sorted(REGISTRY))
        raise ValueError(f"不支持的图种 '{diagram_type}'，当前可用：{avail}")
    return REGISTRY[diagram_type]
