"""
实时协作白板
支持绘图、形状、文本和实时同步
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import uuid
from enum import Enum
import math

logger = logging.getLogger(__name__)


class ShapeType(Enum):
    """形状类型"""
    RECTANGLE = "rectangle"
    CIRCLE = "circle"
    LINE = "line"
    ARROW = "arrow"
    TEXT = "text"
    FREEHAND = "freehand"
    IMAGE = "image"


class DrawingTool(Enum):
    """绘图工具"""
    SELECT = "select"
    PEN = "pen"
    ERASER = "eraser"
    TEXT = "text"
    SHAPE = "shape"
    IMAGE = "image"


@dataclass
class Point:
    """点坐标"""
    x: float
    y: float

    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y}


@dataclass
class BoundingBox:
    """边界框"""
    x: float
    y: float
    width: float
    height: float

    def contains(self, point: Point) -> bool:
        return (
            self.x <= point.x <= self.x + self.width and
            self.y <= point.y <= self.y + self.height
        )


@dataclass
class DrawingElement:
    """绘图元素"""
    id: str
    type: ShapeType
    points: List[Point]
    style: Dict[str, Any] = field(default_factory=dict)
    text: str = ""
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)
    locked: bool = False
    locked_by: str = ""

    def get_bounds(self) -> BoundingBox:
        """获取边界框"""
        if not self.points:
            return BoundingBox(0, 0, 0, 0)

        min_x = min(p.x for p in self.points)
        max_x = max(p.x for p in self.points)
        min_y = min(p.y for p in self.points)
        max_y = max(p.y for p in self.points)

        return BoundingBox(
            min_x,
            min_y,
            max_x - min_x,
            max_y - min_y
        )


class Whiteboard:
    """协作白板"""

    def __init__(self, id: str, name: str = "New Whiteboard"):
        self.id = id
        self.name = name
        self.elements: Dict[str, DrawingElement] = {}
        self.layers: List[Set[str]] = [set()]  # 图层
        self.active_layer = 0
        self.background_color = "#ffffff"
        self.grid_enabled = False
        self.grid_size = 20
        self.version = 0
        self.created_at = datetime.now()
        self.modified_at = datetime.now()

    async def add_element(self, element: DrawingElement) -> str:
        """添加元素"""
        self.elements[element.id] = element
        self.layers[self.active_layer].add(element.id)
        self.version += 1
        self.modified_at = datetime.now()
        return element.id

    async def update_element(
        self,
        element_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """更新元素"""
        element = self.elements.get(element_id)
        if not element or element.locked:
            return False

        # 更新属性
        for key, value in updates.items():
            if hasattr(element, key):
                setattr(element, key, value)

        element.modified_at = datetime.now()
        self.version += 1
        self.modified_at = datetime.now()
        return True

    async def delete_element(self, element_id: str) -> bool:
        """删除元素"""
        if element_id not in self.elements:
            return False

        element = self.elements[element_id]
        if element.locked:
            return False

        # 从所有图层移除
        for layer in self.layers:
            layer.discard(element_id)

        # 删除元素
        del self.elements[element_id]
        self.version += 1
        self.modified_at = datetime.now()
        return True

    async def move_element(
        self,
        element_id: str,
        dx: float,
        dy: float
    ) -> bool:
        """移动元素"""
        element = self.elements.get(element_id)
        if not element or element.locked:
            return False

        # 移动所有点
        for point in element.points:
            point.x += dx
            point.y += dy

        element.modified_at = datetime.now()
        self.version += 1
        self.modified_at = datetime.now()
        return True

    async def get_elements_at(self, point: Point) -> List[DrawingElement]:
        """获取指定位置的元素"""
        elements_at = []
        # 按图层顺序从上到下检查
        for layer in reversed(self.layers):
            for element_id in layer:
                element = self.elements.get(element_id)
                if element and self._point_in_element(point, element):
                    elements_at.append(element)

        return elements_at

    async def get_elements_in_bounds(
        self,
        bounds: BoundingBox
    ) -> List[DrawingElement]:
        """获取边界框内的元素"""
        elements_in = []
        for element in self.elements.values():
            element_bounds = element.get_bounds()
            if self._bounds_intersect(bounds, element_bounds):
                elements_in.append(element)

        return elements_in

    def _point_in_element(self, point: Point, element: DrawingElement) -> bool:
        """检查点是否在元素内"""
        bounds = element.get_bounds()
        return bounds.contains(point)

    def _bounds_intersect(
        self,
        bounds1: BoundingBox,
        bounds2: BoundingBox
    ) -> bool:
        """检查边界框是否相交"""
        return not (
            bounds1.x + bounds1.width < bounds2.x or
            bounds2.x + bounds2.width < bounds1.x or
            bounds1.y + bounds1.height < bounds2.y or
            bounds2.y + bounds2.height < bounds1.y
        )


class WhiteboardManager:
    """白板管理器"""

    def __init__(self):
        self.whiteboards: Dict[str, Whiteboard] = {}
        self.user_cursors: Dict[str, Dict[str, Point]] = defaultdict(dict)  # whiteboard_id -> user_id -> cursor

    async def create_whiteboard(self, name: str = None) -> str:
        """创建白板"""
        whiteboard_id = str(uuid.uuid4())
        name = name or f"Whiteboard {len(self.whiteboards) + 1}"

        whiteboard = Whiteboard(whiteboard_id, name)
        self.whiteboards[whiteboard_id] = whiteboard

        logger.info(f"Created whiteboard {whiteboard_id}: {name}")
        return whiteboard_id

    async def get_whiteboard(self, whiteboard_id: str) -> Optional[Whiteboard]:
        """获取白板"""
        return self.whiteboards.get(whiteboard_id)

    async def delete_whiteboard(self, whiteboard_id: str) -> bool:
        """删除白板"""
        if whiteboard_id not in self.whiteboards:
            return False

        del self.whiteboards[whiteboard_id]
        del self.user_cursors[whiteboard_id]

        logger.info(f"Deleted whiteboard {whiteboard_id}")
        return True

    async def add_shape(
        self,
        whiteboard_id: str,
        shape_type: ShapeType,
        points: List[Tuple[float, float]],
        style: Dict[str, Any] = None,
        user_id: str = ""
    ) -> Optional[str]:
        """添加形状"""
        whiteboard = self.whiteboards.get(whiteboard_id)
        if not whiteboard:
            return None

        # 转换点坐标
        point_objects = [Point(x, y) for x, y in points]

        # 创建元素
        element = DrawingElement(
            id=str(uuid.uuid4()),
            type=shape_type,
            points=point_objects,
            style=style or {
                "stroke_color": "#000000",
                "stroke_width": 2,
                "fill_color": "transparent"
            },
            created_by=user_id
        )

        return await whiteboard.add_element(element)

    async def add_text(
        self,
        whiteboard_id: str,
        text: str,
        position: Tuple[float, float],
        style: Dict[str, Any] = None,
        user_id: str = ""
    ) -> Optional[str]:
        """添加文本"""
        whiteboard = self.whiteboards.get(whiteboard_id)
        if not whiteboard:
            return None

        point = Point(position[0], position[1])

        element = DrawingElement(
            id=str(uuid.uuid4()),
            type=ShapeType.TEXT,
            points=[point],
            text=text,
            style=style or {
                "font_family": "Arial",
                "font_size": 16,
                "color": "#000000"
            },
            created_by=user_id
        )

        return await whiteboard.add_element(element)

    async def add_freehand(
        self,
        whiteboard_id: str,
        points: List[Tuple[float, float]],
        style: Dict[str, Any] = None,
        user_id: str = ""
    ) -> Optional[str]:
        """添加自由绘画"""
        whiteboard = self.whiteboards.get(whiteboard_id)
        if not whiteboard:
            return None

        # 平滑处理点
        smoothed_points = self._smooth_points(points)

        point_objects = [Point(x, y) for x, y in smoothed_points]

        element = DrawingElement(
            id=str(uuid.uuid4()),
            type=ShapeType.FREEHAND,
            points=point_objects,
            style=style or {
                "stroke_color": "#000000",
                "stroke_width": 2
            },
            created_by=user_id
        )

        return await whiteboard.add_element(element)

    def _smooth_points(
        self,
        points: List[Tuple[float, float]],
        window_size: int = 3
    ) -> List[Tuple[float, float]]:
        """平滑点序列"""
        if len(points) < window_size:
            return points

        smoothed = []
        half_window = window_size // 2

        for i in range(len(points)):
            start = max(0, i - half_window)
            end = min(len(points), i + half_window + 1)

            avg_x = sum(p[0] for p in points[start:end]) / (end - start)
            avg_y = sum(p[1] for p in points[start:end]) / (end - start)

            smoothed.append((avg_x, avg_y))

        return smoothed

    async def update_element(
        self,
        whiteboard_id: str,
        element_id: str,
        updates: Dict[str, Any],
        user_id: str = ""
    ) -> bool:
        """更新元素"""
        whiteboard = self.whiteboards.get(whiteboard_id)
        if not whiteboard:
            return False

        # 检查锁定状态
        element = whiteboard.elements.get(element_id)
        if element and element.locked and element.locked_by != user_id:
            return False

        return await whiteboard.update_element(element_id, updates)

    async def delete_element(
        self,
        whiteboard_id: str,
        element_id: str,
        user_id: str = ""
    ) -> bool:
        """删除元素"""
        whiteboard = self.whiteboards.get(whiteboard_id)
        if not whiteboard:
            return False

        # 检查锁定状态
        element = whiteboard.elements.get(element_id)
        if element and element.locked and element.locked_by != user_id:
            return False

        return await whiteboard.delete_element(element_id)

    async def move_elements(
        self,
        whiteboard_id: str,
        element_ids: List[str],
        dx: float,
        dy: float,
        user_id: str = ""
    ) -> int:
        """移动多个元素"""
        whiteboard = self.whiteboards.get(whiteboard_id)
        if not whiteboard:
            return 0

        moved_count = 0
        for element_id in element_ids:
            element = whiteboard.elements.get(element_id)
            if element and (not element.locked or element.locked_by == user_id):
                if await whiteboard.move_element(element_id, dx, dy):
                    moved_count += 1

        return moved_count

    async def lock_element(
        self,
        whiteboard_id: str,
        element_id: str,
        user_id: str = ""
    ) -> bool:
        """锁定元素"""
        whiteboard = self.whiteboards.get(whiteboard_id)
        if not whiteboard:
            return False

        element = whiteboard.elements.get(element_id)
        if not element:
            return False

        if element.locked and element.locked_by != user_id:
            return False

        element.locked = True
        element.locked_by = user_id
        element.modified_at = datetime.now()
        whiteboard.version += 1

        return True

    async def unlock_element(
        self,
        whiteboard_id: str,
        element_id: str,
        user_id: str = ""
    ) -> bool:
        """解锁元素"""
        whiteboard = self.whiteboards.get(whiteboard_id)
        if not whiteboard:
            return False

        element = whiteboard.elements.get(element_id)
        if not element or element.locked_by != user_id:
            return False

        element.locked = False
        element.locked_by = ""
        element.modified_at = datetime.now()
        whiteboard.version += 1

        return True

    async def update_user_cursor(
        self,
        whiteboard_id: str,
        user_id: str,
        x: float,
        y: float
    ):
        """更新用户光标位置"""
        if whiteboard_id not in self.user_cursors:
            self.user_cursors[whiteboard_id] = {}

        self.user_cursors[whiteboard_id][user_id] = Point(x, y)

    async def get_user_cursor(
        self,
        whiteboard_id: str,
        user_id: str
    ) -> Optional[Point]:
        """获取用户光标位置"""
        return self.user_cursors.get(whiteboard_id, {}).get(user_id)

    async def export_whiteboard(
        self,
        whiteboard_id: str,
        format: str = "json"
    ) -> Optional[Dict[str, Any]]:
        """导出白板"""
        whiteboard = self.whiteboards.get(whiteboard_id)
        if not whiteboard:
            return None

        if format == "json":
            return {
                "id": whiteboard.id,
                "name": whiteboard.name,
                "elements": [
                    {
                        "id": elem.id,
                        "type": elem.type.value,
                        "points": [p.to_dict() for p in elem.points],
                        "text": elem.text,
                        "style": elem.style,
                        "created_by": elem.created_by,
                        "created_at": elem.created_at.isoformat(),
                        "modified_at": elem.modified_at.isoformat(),
                        "locked": elem.locked,
                        "locked_by": elem.locked_by
                    }
                    for elem in whiteboard.elements.values()
                ],
                "layers": [
                    list(layer) for layer in whiteboard.layers
                ],
                "background_color": whiteboard.background_color,
                "grid_enabled": whiteboard.grid_enabled,
                "grid_size": whiteboard.grid_size,
                "version": whiteboard.version,
                "created_at": whiteboard.created_at.isoformat(),
                "modified_at": whiteboard.modified_at.isoformat()
            }

        # TODO: 支持其他格式如SVG、PNG

        return None

    async def get_whiteboard_state(
        self,
        whiteboard_id: str,
        since_version: int = 0
    ) -> Optional[Dict[str, Any]]:
        """获取白板状态增量"""
        whiteboard = self.whiteboards.get(whiteboard_id)
        if not whiteboard or whiteboard.version <= since_version:
            return None

        # 返回变更的元素
        changed_elements = []
        for element in whiteboard.elements.values():
            # 简化处理：返回所有元素（实际应该基于版本过滤）
            changed_elements.append({
                "id": element.id,
                "type": element.type.value,
                "points": [p.to_dict() for p in element.points],
                "text": element.text,
                "style": element.style,
                "created_by": element.created_by,
                "created_at": element.created_at.isoformat(),
                "modified_at": element.modified_at.isoformat(),
                "locked": element.locked,
                "locked_by": element.locked_by
            })

        return {
            "version": whiteboard.version,
            "elements": changed_elements,
            "deleted_elements": [],  # TODO: 跟踪删除的元素
            "background_color": whiteboard.background_color,
            "grid_enabled": whiteboard.grid_enabled
        }


# 全局实例
whiteboard_manager = WhiteboardManager()