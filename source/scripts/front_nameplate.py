"""Five-course NP3 keyed message and logo modules; frozen MSG-SLOT-1 is separate."""

import hashlib
import json
from pathlib import Path

import FreeCAD as App
import Part

from letter_metrics import straight_strokes, text_faces

V = App.Vector
ROOT = Path(__file__).resolve().parents[1]


def rect_wire(x0, y0, x1, y1, z):
    return Part.makePolygon([V(x0, y0, z), V(x1, y0, z), V(x1, y1, z),
                             V(x0, y1, z), V(x0, y0, z)])


def module_settings(spec, parameters):
    values = {**parameters["message"], "width": spec["width"]}
    if spec["kind"] == "front_fit_plaque":
        values["height"] = 9.2
    if spec["kind"] == "front_logo":
        values["back_y"] = parameters["logo"]["back_y"]
    return values


def carrier(message):
    width, h = message["width"], message["height"]
    taper, margin = message["side_taper"], message["rear_vertical_margin"]
    flat, thickness = message["rear_flat_thickness"], message["thickness"]
    return Part.makeLoft([
        rect_wire(0, margin, width, h - margin, 0),
        rect_wire(taper * flat / thickness, margin, width - taper * flat / thickness, h - margin, flat),
        rect_wire(taper, 0, width - taper, h, thickness),
    ], True, True)


def message_faces(spec, parameters):
    message = parameters["message"]
    font = ROOT / message["font"]
    results = []
    for text, size, target_height, baseline in zip(message["lines"], spec["text_sizes"],
                                                  spec["text_heights"], message["line_bottoms"]):
        faces = text_faces(text, font, size)
        bound = Part.makeCompound(faces).BoundBox
        if bound.XLength > spec["width"] - 2 * message["side_taper"] - 3.9:
            raise ValueError(f"Display text exceeds the available face width for {spec['id']}; stop rather than truncate or compress.")
        vertical = target_height / bound.YLength
        if vertical < 1 - 1e-8:
            raise ValueError("Do not thin the lettering vertically to force a fit")
        matrix = App.Matrix()
        matrix.A22 = vertical
        faces = [face.transformGeometry(matrix) for face in faces]
        metrics = straight_strokes(faces)
        if min(item["width_mm"] for item in metrics) < message["minimum_straight_stroke"]:
            raise ValueError(f"Printed lettering is too fine for {spec['id']}; stop and review the layout.")
        bound = Part.makeCompound(faces).BoundBox
        translation = V((spec["width"] - bound.XLength) / 2 - bound.XMin,
                        baseline - bound.YMin, message["thickness"])
        for face in faces:
            face.translate(translation)
        results.append((text, faces, metrics))
    return results


def plaque_shape(spec, parameters):
    body = carrier(module_settings(spec, parameters))
    raised = [face.extrude(V(0, 0, parameters["message"]["relief"]))
              for _, faces, _ in message_faces(spec, parameters) for face in faces]
    return body.multiFuse(raised).removeSplitter()


def logo_shape(spec, parameters):
    message = module_settings(spec, parameters)
    logo = parameters["logo"]
    body = carrier(message)
    origin = V(message["width"] / 2, message["height"] / 2, message["thickness"])
    diameter = spec["diameter"]
    disc = Part.makeCylinder(diameter / 2, logo["disc_height"], origin)
    data = json.loads((ROOT / logo["outline"]).read_text())
    raised = []
    for polygon in data["polygons"]:
        wires = []
        for ring in polygon:
            points = [V(origin.x + x * diameter, origin.y + y * diameter,
                        origin.z + logo["disc_height"]) for x, y in ring]
            if (points[-1] - points[0]).Length > 1e-8:
                points.append(points[0])
            wires.append(Part.makePolygon(points))
        face = Part.makeFace(wires, "Part::FaceMakerBullseye")
        raised.append(face.extrude(V(0, 0, logo["relief"])))
    return body.multiFuse([disc, *raised]).removeSplitter()


def groove_cutter(message, slot, bottom_course):
    width, x = slot["width"], slot["x"]
    c = slot.get("clearance", message["clearance"])
    thickness, taper = message["thickness"], message["side_taper"]
    back_y = slot["back_y"]
    face_y = back_y - thickness
    flat_y = back_y - message["rear_flat_thickness"]
    z0 = slot.get("bottom_z", message["bottom_z"])
    profiles = [
        (0.0, taper - c, z0 - .2),
        (face_y, taper - c, z0),
        (flat_y, taper * message["rear_flat_thickness"] / thickness - c,
         z0 + message["rear_vertical_margin"]),
        (back_y, -c, z0 + message["rear_vertical_margin"]),
        (back_y + c, -c, z0 + message["rear_vertical_margin"]),
    ]
    wires = []
    for y, inset, lower in profiles:
        lower = lower if bottom_course else -1
        wires.append(Part.makePolygon([
            V(x + inset, y, lower), V(x + width - inset, y, lower),
            V(x + width - inset, y, 9.6), V(x + inset, y, 9.6),
            V(x + inset, y, lower),
        ]))
    return Part.makeLoft(wires, True, True)


def front_base(spec, parameters, make_brick):
    message = parameters["message"]
    nx, ny = spec["studs"]
    width = nx * parameters["interface"]["pitch"]
    body = make_brick({**spec, "kind": "brick"}, parameters)
    body = body.cut(Part.makeBox(width + 2, 8, 2.1, V(-1, 0, spec["height"])))
    body = body.fuse(Part.makeBox(width - .2, message["front_beam_depth"], spec["height"],
                                 V(.1, .1, 0))).removeSplitter()
    for slot in spec["slots"]:
        body = body.cut(groove_cutter(message, slot, spec["bottom_course"]))
    return body.removeSplitter()


def keeper_shape(parameters, make_brick):
    socket = make_brick({"id": "NP3-KEEPER", "kind": "brick", "studs": [2, 1], "height": 3.2,
                        "socket": True, "top_studs": False}, parameters)
    socket.translate(V(0, 8, 0))
    return socket.fuse(Part.makeBox(15.8, 8.1, 3.2, V(.1, .1, 0))).removeSplitter()


def shape_for_front(spec, parameters, make_brick):
    if spec["kind"] in ("front_base", "front_fit_socket"):
        return front_base(spec, parameters, make_brick)
    if spec["kind"] == "front_plaque":
        return plaque_shape(spec, parameters)
    if spec["kind"] == "front_logo":
        return logo_shape(spec, parameters)
    if spec["kind"] == "front_fit_plaque":
        return carrier(module_settings(spec, parameters))
    if spec["kind"] == "front_keeper":
        return keeper_shape(parameters, make_brick)
    raise ValueError(f"Unknown front-module kind: {spec['kind']}")
