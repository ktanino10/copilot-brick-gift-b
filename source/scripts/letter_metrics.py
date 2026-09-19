"""Measure actual raised-letter straight strokes, not a font-size approximation."""

import Part


def text_faces(text, font, size):
    return [Part.makeFace(wires, "Part::FaceMakerBullseye")
            for wires in Part.makeWireString(text, str(font), size, 0) if wires]


def inside_polygon(x, y, vertices):
    inside = False
    for a, b in zip(vertices, vertices[1:] + vertices[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


def straight_strokes(faces):
    gauges = []
    for index, face in enumerate(faces):
        polygons = [[(p.x, p.y) for p in wire.discretize(Deflection=.005)] for wire in face.Wires]
        segments = [[], []]
        for edge in face.Edges:
            if len(edge.Vertexes) != 2:
                continue
            a, b = [vertex.Point for vertex in edge.Vertexes]
            if abs(edge.Length - (b - a).Length) > 1e-6:
                continue
            if abs(a.x - b.x) < 1e-6 and abs(a.y - b.y) > .5:
                segments[0].append((a.x, min(a.y, b.y), max(a.y, b.y)))
            if abs(a.y - b.y) < 1e-6 and abs(a.x - b.x) > .5:
                segments[1].append((a.y, min(a.x, b.x), max(a.x, b.x)))
        for axis, edges in enumerate(segments):
            for i, a in enumerate(edges):
                for b in edges[i + 1:]:
                    width = abs(a[0] - b[0])
                    low, high = max(a[1], b[1]), min(a[2], b[2])
                    if not .05 < width < 4 or high - low < .5:
                        continue
                    samples = [(a[0] + f * (b[0] - a[0]), (low + high) / 2)
                               for f in (.1, .3, .5, .7, .9)]
                    if axis:
                        samples = [(y, x) for x, y in samples]
                    if all(sum(inside_polygon(x, y, poly) for poly in polygons) % 2 for x, y in samples):
                        gauges.append({"face": index, "axis": "XY"[axis],
                                       "width_mm": width, "overlap_mm": high - low})
    if not gauges:
        raise ValueError("No reliable parallel straight-stroke gauges in the actual letter faces")
    return gauges
