"""Neutral approved nameplate-legibility operations; no recipient data or file access."""

import numpy as np
from scipy import ndimage
from shapely import affinity, contains_xy, maximum_inscribed_circle
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pieces(geometry):
    return list(geometry.geoms) if hasattr(geometry, "geoms") else (
        [] if geometry.is_empty else [geometry]
    )


def closed_ring(points):
    require(len(points) >= 4 and np.linalg.norm(np.array(points[0]) - points[-1]) < 1e-8,
            "A CAD boundary is not a sampled closed wire.")
    return [*points[:-1], points[0]]


def contour_polygon(outer, holes=()):
    return Polygon(closed_ring(outer), [closed_ring(hole) for hole in holes])


def ink_shape(glyph):
    shape = unary_union([contour_polygon(face["outer"], face["holes"]) for face in glyph["faces"]])
    require(shape.is_valid and not shape.is_empty, "Invalid CAD glyph contours; do not repair silently.")
    return shape


def central_chords(polygon):
    x0, y0, x1, y1 = polygon.bounds
    samples_y = np.linspace(y0 + .25 * (y1 - y0), y0 + .75 * (y1 - y0), 101)
    samples_x = np.linspace(x0 + .25 * (x1 - x0), x0 + .75 * (x1 - x0), 101)
    horizontal = [
        max((item.length for item in pieces(polygon.intersection(
            LineString([(x0 - 1, y), (x1 + 1, y)])
        ))), default=0) for y in samples_y
    ]
    vertical = [
        max((item.length for item in pieces(polygon.intersection(
            LineString([(x, y0 - 1), (x, y1 + 1)])
        ))), default=0) for x in samples_x
    ]
    require(min(horizontal + vertical) > 0, "Unsupported non-contiguous counter measurement.")
    return min(horizontal), min(vertical)


def aperture_pocket(ink):
    hull = ink.convex_hull
    pockets = [item for item in pieces(hull.difference(ink))
               if item.geom_type == "Polygon"
               and item.boundary.intersection(hull.boundary).length > .1]
    require(bool(pockets), "Expected an open c/e pocket in the selected font.")
    return max(pockets, key=lambda item: item.area)


def aperture_width(ink, grid=.01):
    pocket = aperture_pocket(ink)
    seed = maximum_inscribed_circle(pocket, tolerance=.001).coords[0]
    x0, y0, x1, y1 = ink.bounds
    xs = np.arange(x0 - .1, x1 + 2 + grid, grid)
    ys = np.arange(y0 - .1, y1 + .1 + grid, grid)
    xx, yy = np.meshgrid(xs, ys)
    free = ~contains_xy(ink, xx, yy)
    distance = ndimage.distance_transform_edt(free, sampling=grid)
    iy = int(round((seed[1] - ys[0]) / grid))
    ix = int(round((seed[0] - xs[0]) / grid))
    low, high = 0.0, float(distance[iy, ix])
    for _ in range(16):
        radius = (low + high) / 2
        labels, _ = ndimage.label(free & (distance >= radius))
        origin = labels[iy, ix]
        if origin and np.any(labels[:, -1] == origin):
            low = radius
        else:
            high = radius
    return 2 * low


def material_core_split(ink):
    for radius in np.arange(.2, 1.201, .005):
        for component in pieces(ink):
            cores = [item for item in pieces(component.buffer(-float(radius)))
                     if item.area >= .05]
            if len(cores) > 1:
                return 2 * float(radius)
    return None


def plan_rows(raw_rows, goal, maximum_ink_width_mm):
    rows = []
    for row in raw_rows:
        glyph_plans = []
        previous = None
        shift = 0.0
        geometries = []
        for glyph in row["glyphs"]:
            original = ink_shape(glyph)
            ink = original
            operation = {"index": glyph["index"], "character": glyph["character"], "counters": []}
            for face_index, face in enumerate(glyph["faces"]):
                for hole_index, points in enumerate(face["holes"]):
                    hole = contour_polygon(points)
                    horizontal, vertical = central_chords(hole)
                    sx = max(1.0, goal["counter_central_half_chord"] / horizontal)
                    sy = max(1.0, goal["counter_central_half_chord"] / vertical)
                    if max(sx, sy) > 1.000001:
                        bounds = hole.bounds
                        center = [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2]
                        enlarged = affinity.scale(hole, xfact=sx, yfact=sy, origin=tuple(center))
                        ink = ink.difference(enlarged)
                        operation["counters"].append({
                            "face_index": face_index, "hole_index": hole_index,
                            "center_xy": center, "scale_xy": [sx, sy],
                        })
            if glyph["character"] == "e":
                pocket = aperture_pocket(ink)
                seed = maximum_inscribed_circle(pocket, tolerance=.001).coords[0]
                x0, y0, x1, y1 = ink.bounds
                free = LineString([(seed[0], y0 - 1), (seed[0], y1 + 1)]).difference(ink)
                chamber = [segment for segment in pieces(free) if segment.distance(Point(seed)) < .00001]
                require(len(chamber) == 1, "Cannot identify the e aperture without guessing.")
                top = chamber[0].bounds[3]
                rectangle = [seed[0], top - goal["e_exit_channel"], x1 + .1, top]
                ink = ink.difference(box(*rectangle))
                operation["e_channel"] = rectangle
            require(ink.is_valid and len(pieces(ink)) == len(pieces(original)),
                    "Candidate edit changes a glyph's connected components.")
            moved = affinity.translate(ink, xoff=shift)
            if previous is not None and previous.distance(moved) < goal["adjacent_glyph_clearance"]:
                low, high = 0.0, 2.0
                require(previous.distance(affinity.translate(moved, xoff=high)) >= goal["adjacent_glyph_clearance"],
                        "An unexpected kerning overlap exceeds the supported spacing adjustment.")
                for _ in range(32):
                    offset = (low + high) / 2
                    if previous.distance(affinity.translate(moved, xoff=offset)) < goal["adjacent_glyph_clearance"]:
                        low = offset
                    else:
                        high = offset
                shift += high
                moved = affinity.translate(moved, xoff=high)
            operation["extra_x_mm"] = shift
            previous = moved
            geometries.append(moved)
            glyph_plans.append(operation)
        bounds = unary_union(geometries).bounds
        width = bounds[2] - bounds[0]
        require(width <= maximum_ink_width_mm + .0001,
                f"Lettering width{width:.6f}mm exceeds available{maximum_ink_width_mm:.6f}mm; do not shrink or truncate.")
        rows.append({"row": row["number"], "width_mm": width, "glyphs": glyph_plans})
    return rows
