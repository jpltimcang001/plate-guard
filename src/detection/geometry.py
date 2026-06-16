"""Geometry utilities for detection — point-in-polygon and IOU.

These functions are extracted to a separate module to avoid circular
imports between ``zone_validator`` (which imports ``Zone``) and
``zone`` (which needs ``point_in_polygon``).
"""

from __future__ import annotations


def point_in_polygon(
    px: float,
    py: float,
    polygon: list[tuple[float, float]],
) -> bool:
    """Ray-casting point-in-polygon test.

    Args:
        px: X-coordinate of the point.
        py: Y-coordinate of the point.
        polygon: List of ``(x, y)`` vertices in clockwise or
            counter-clockwise order (at least 3 points).

    Returns:
        ``True`` if the point lies inside the polygon (including
        the boundary), ``False`` otherwise.

    """
    if len(polygon) < 3:
        return False

    inside = False
    n = len(polygon)
    j = n - 1

    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        # Check if the point is exactly on a vertex
        if (px == xi and py == yi) or (px == xj and py == yj):
            return True

        # Check intersection of the horizontal ray at py with edge (i, j)
        if (yi > py) != (yj > py):
            if yi != yj:
                x_intersect = xj + (xi - xj) * (py - yj) / (yi - yj)
            else:
                x_intersect = float("inf")
            if px == x_intersect:
                # Point is exactly on the edge
                return True
            if px < x_intersect:
                inside = not inside

        j = i

    return inside


def compute_iou(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> float:
    """Compute the Intersection-over-Union of two bounding boxes.

    Args:
        a: Bounding box ``(x1, y1, x2, y2)``.
        b: Bounding box ``(x1, y1, x2, y2)``.

    Returns:
        IOU value in ``[0.0, 1.0]``.  Returns ``0.0`` if there is
        no overlap.

    """
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter_area = (ix2 - ix1) * (iy2 - iy1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0

    return inter_area / union_area
