"""Export a single actual STL as unsliced, centered, black-to-white geometry."""

from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
ET.register_namespace("", NS)


def write_single_3mf(stl, destination, part_id, boundary=2.4):
    data = Path(stl).read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + count * 50:
        raise ValueError("Expected an intact binary STL.")
    records = np.frombuffer(data, dtype=np.dtype([
        ("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")
    ]), offset=84, count=count)
    points = records["vertices"].reshape(-1, 3).astype(float)
    vertices, indices = np.unique(points, axis=0, return_inverse=True)
    lower, upper = vertices.min(axis=0), vertices.max(axis=0)
    if not np.isfinite(vertices).all() or abs(lower[2]) > 1e-6:
        raise ValueError("The STL must already have its flat rear at Z=0.")
    offset = [(256 - upper[axis] - lower[axis]) / 2 for axis in (0, 1)] + [0]
    model = ET.Element(f"{{{NS}}}model", unit="millimeter")
    ET.SubElement(model, f"{{{NS}}}metadata", name="Title").text = part_id
    ET.SubElement(model, f"{{{NS}}}metadata", name="Description").text = (
        f"NOT_SLICED. One part, rear on bed, relief up. Start black; manually add Pause "
        f"after the support at {boundary:g}mm and before the first white path. "
        "No Pause, printer profile or G-code is encoded. Physical print/fit unverified."
    )
    resources = ET.SubElement(model, f"{{{NS}}}resources")
    materials = ET.SubElement(resources, f"{{{NS}}}basematerials", id="1")
    ET.SubElement(materials, f"{{{NS}}}base", name="black", displaycolor="#171D28FF")
    obj = ET.SubElement(resources, f"{{{NS}}}object", id="2", type="model", name=part_id, pid="1", pindex="0")
    mesh = ET.SubElement(obj, f"{{{NS}}}mesh")
    nodes = ET.SubElement(mesh, f"{{{NS}}}vertices")
    for point in vertices:
        ET.SubElement(nodes, f"{{{NS}}}vertex", **dict(zip("xyz", (f"{value:.6f}" for value in point))))
    nodes = ET.SubElement(mesh, f"{{{NS}}}triangles")
    for face in indices.reshape(-1, 3):
        ET.SubElement(nodes, f"{{{NS}}}triangle", **dict(zip(("v1", "v2", "v3"), map(str, face))))
    build = ET.SubElement(model, f"{{{NS}}}build")
    ET.SubElement(build, f"{{{NS}}}item", objectid="2",
                  transform="1 0 0 0 1 0 0 0 1 " + " ".join(f"{value:.6f}" for value in offset))
    members = {
        "[Content_Types].xml": b'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>',
        "_rels/.rels": b'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>',
        "3D/3dmodel.model": ET.tostring(model, encoding="utf-8", xml_declaration=True),
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in members.items():
            info = zipfile.ZipInfo(name, (2026, 9, 22, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    return {"position": offset, "bounds_mm": [lower.tolist(), upper.tolist()], "quantity": 1}
