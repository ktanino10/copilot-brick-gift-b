"""Neutral approved nameplate-legibility operations; no recipient data or file access."""

import FreeCAD as App
import Part


def require(condition, message):
    if not condition:
        raise ValueError(message)


def face_data(shape):
    result = []
    for face in shape.Faces:
        outer = face.OuterWire
        points = lambda wire: [[p.x, p.y] for p in wire.discretize(Deflection=.002)]
        result.append({
            "outer": points(outer),
            "holes": [points(wire) for wire in face.Wires if not wire.isSame(outer)],
        })
    return result


def raw_row(text, font, size, height, uniform):
    groups = Part.makeWireString(text, str(font), size, 0)
    require(len(groups) == len(text), "Font glyph count does not preserve the exact string.")
    shapes = [(index, text[index], Part.makeFace(wires, "Part::FaceMakerBullseye"))
              for index, wires in enumerate(groups) if wires]
    bounds = Part.makeCompound([shape for _, _, shape in shapes]).BoundBox
    sy = height / bounds.YLength
    sx = sy if uniform else 1.0
    matrix = App.Matrix()
    matrix.A11, matrix.A22 = sx, sy
    shapes = [(index, char, shape.transformGeometry(matrix)) for index, char, shape in shapes]
    bounds = Part.makeCompound([shape for _, _, shape in shapes]).BoundBox
    for _, _, shape in shapes:
        shape.translate(App.Vector(-bounds.XMin, -bounds.YMin, 0))
    return shapes, sx, sy


def edited_glyph(shape, operations):
    cuts = []
    for spec in operations["counters"]:
        face = shape.Faces[spec["face_index"]]
        holes = [wire for wire in face.Wires if not wire.isSame(face.OuterWire)]
        hole = Part.Face(holes[spec["hole_index"]])
        center = App.Vector(*spec["center_xy"], 0)
        hole.translate(-center)
        matrix = App.Matrix()
        matrix.A11, matrix.A22 = spec["scale_xy"]
        hole = hole.transformGeometry(matrix)
        hole.translate(center)
        cuts.append(hole)
    if operations.get("e_channel"):
        x0, y0, x1, y1 = operations["e_channel"]
        cuts.append(Part.Face(Part.makePolygon([
            App.Vector(x0, y0, 0), App.Vector(x1, y0, 0),
            App.Vector(x1, y1, 0), App.Vector(x0, y1, 0), App.Vector(x0, y0, 0),
        ])))
    for cutter in cuts:
        shape = shape.cut(cutter).removeSplitter()
    require(shape.isValid() and shape.Area > 0, "A counter edit produced an invalid glyph.")
    return shape
