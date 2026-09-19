"""Actual OpenCASCADE solids used by every exported/viewed representation."""

from __future__ import annotations

import math
from pathlib import Path

import FreeCAD as App
import Part

V = App.Vector


def rectangle(x0, y0, x1, y1, z):
    return Part.makePolygon([V(x0, y0, z), V(x1, y0, z), V(x1, y1, z),
                             V(x0, y1, z), V(x0, y0, z)])


def socket_cutter(nx, ny, depth, interface, clearance):
    pitch = interface["pitch"]
    edge = pitch / 2 - interface["reference_stud_diameter"] / 2 - clearance
    lead = interface["socket_lead_in"]
    lead_h = interface["socket_lead_in_height"]
    main = Part.makeBox(nx * pitch - 2 * edge, ny * pitch - 2 * edge, depth,
                        V(edge, edge, 0))
    entry = Part.makeLoft([
        rectangle(edge - lead, edge - lead, nx * pitch - edge + lead,
                  ny * pitch - edge + lead, 0),
        rectangle(edge, edge, nx * pitch - edge, ny * pitch - edge, lead_h),
    ], True)
    return main.fuse(entry)


def supports(nx, ny, depth, interface, clearance):
    pitch = interface["pitch"]
    reference_r = interface["reference_stud_diameter"] / 2
    lead = interface["socket_lead_in"]
    lead_h = interface["socket_lead_in_height"]
    pieces = []
    holes = []
    if nx > 1 and ny > 1:
        radius = pitch / math.sqrt(2) - reference_r - clearance
        for x in range(1, nx):
            for y in range(1, ny):
                origin = V(x * pitch, y * pitch, 0)
                tube = Part.makeCone(radius - lead, radius, lead_h, origin).fuse(
                    Part.makeCylinder(radius, depth - lead_h,
                                      origin + V(0, 0, lead_h)))
                inner = Part.makeCylinder(interface["tube_inner_diameter"] / 2,
                                          depth, origin)
                holes.append(inner)
                pieces.append(tube.cut(inner))
    elif max(nx, ny) > 1:
        radius = pitch / 2 - reference_r - clearance
        for i in range(1, max(nx, ny)):
            origin = V(i * pitch if nx > 1 else pitch / 2,
                       i * pitch if ny > 1 else pitch / 2, 0)
            pieces.append(Part.makeCone(radius - lead, radius, lead_h, origin).fuse(
                Part.makeCylinder(radius, depth - lead_h, origin + V(0, 0, lead_h))))
    edge = pitch / 2 - reference_r - clearance
    rib_width = interface["roof_support_rib_width"]
    hole_group = Part.makeCompound(holes) if holes else None
    # The grid ribs bound first-roof-layer spans; tubes alone leave long corridors.
    for x in range(1, nx):
        rib = Part.makeBox(rib_width, ny * pitch - 2 * edge, depth,
                          V(x * pitch - rib_width / 2, edge, 0))
        pieces.append(rib.cut(hole_group) if holes else rib)
    for y in range(1, ny):
        rib = Part.makeBox(nx * pitch - 2 * edge, rib_width, depth,
                          V(edge, y * pitch - rib_width / 2, 0))
        pieces.append(rib.cut(hole_group) if holes else rib)
    return pieces


def stud_shape(x, y, z, interface, diameter_correction=None):
    correction = (interface["stud_diameter_correction"] if diameter_correction is None
                  else diameter_correction)
    radius = (interface["reference_stud_diameter"] + correction) / 2
    lead = interface["stud_lead_in"]
    origin = V(x, y, z)
    return Part.makeCylinder(radius, interface["stud_height"] - lead, origin).fuse(
        Part.makeCone(radius, radius - lead, lead,
                      origin + V(0, 0, interface["stud_height"] - lead)))


def build_brick(spec, parameters):
    i = parameters["interface"]
    nx, ny = spec["studs"]
    height = spec["height"]
    pitch = i["pitch"]
    gap = i["body_gap"]
    body = Part.makeBox(nx * pitch - gap, ny * pitch - gap, height, V(gap / 2, gap / 2, 0))
    additions = []
    if spec["socket"]:
        clearance = spec.get("female_clearance", i["female_radial_clearance"])
        roof = i["thin_plate_roof"] if height <= i["plate_height"] else i["roof"]
        depth = height - roof
        if spec["kind"] == "dock":
            depth = parameters["message"]["dock_socket_depth"]
        body = body.cut(socket_cutter(nx, ny, depth, i, clearance))
        additions += supports(nx, ny, depth, i, clearance)
    if spec["top_studs"]:
        for x in range(nx):
            for y in range(ny):
                additions.append(stud_shape((x + 0.5) * pitch, (y + 0.5) * pitch,
                                            height, i, spec.get("male_correction")))
    if additions:
        body = body.multiFuse(additions).removeSplitter()
    if spec["kind"] == "dock":
        m = parameters["message"]
        slot = Part.makeBox(m["slot_length"], m["slot_width"], m["slot_depth"] + 0.1,
                            V((nx * pitch - m["slot_length"]) / 2,
                              m["slot_center_y"] - m["slot_width"] / 2,
                              height - m["slot_depth"]))
        body = body.cut(slot).removeSplitter()
    return body


def build_card(parameters, root):
    m = parameters["message"]
    width, height, thickness = m["card_width"], m["card_height"], m["card_thickness"]
    font = Path(root) / m["font"]
    if not font.is_file():
        raise FileNotFoundError(f"Required font asset is missing: {m['font']}")
    body = Part.makeBox(width, height, thickness)
    raised = []
    for text, size, baseline in zip(m["lines"], m["text_sizes"], m["text_baselines"]):
        glyphs = Part.makeWireString(text, str(font), size, 0)
        faces = [Part.makeFace(wires, "Part::FaceMakerBullseye") for wires in glyphs if wires]
        word = Part.makeCompound(faces)
        bounds = word.BoundBox
        if bounds.XLength > width - 4:
            raise ValueError(f"Message is too wide at the declared size: {text}")
        word.translate(V((width - bounds.XLength) / 2 - bounds.XMin,
                         baseline - bounds.YMin, thickness))
        raised.append(word.extrude(V(0, 0, m["text_relief"])))
    return body.multiFuse(raised).removeSplitter()


def shape_for(spec, parameters, root):
    if spec["kind"].startswith("front_"):
        from front_nameplate import shape_for_front
        shape = shape_for_front(spec, parameters, build_brick)
    else:
        shape = build_card(parameters, root) if spec["kind"] == "card" else build_brick(spec, parameters)
    if not shape.isValid() or len(shape.Solids) != 1 or shape.Volume <= 0:
        raise ValueError(f"Invalid printable solid: {spec['id']}")
    return shape


def placement_for(instance):
    rx, ry, rz = instance["rotation"]
    rotation = App.Rotation(V(0, 0, 1), rz).multiply(
        App.Rotation(V(0, 1, 0), ry)).multiply(App.Rotation(V(1, 0, 0), rx))
    return App.Placement(V(*instance["position"]), rotation)


def bounds_list(shape):
    b = shape.optimalBoundingBox(False, False)
    return [[round(b.XMin, 6), round(b.YMin, 6), round(b.ZMin, 6)],
            [round(b.XMax, 6), round(b.YMax, 6), round(b.ZMax, 6)]]
