"""Draw actual native contours/sections, not substitute-font illustrations."""

from html import escape
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon, box

PROPOSAL = Path(__file__).resolve().parents[1]
ROOT = PROPOSAL.parents[1]
WORK = ROOT / ".work/plate-v2"


def polygons(shape):
    return list(shape.geoms) if hasattr(shape, "geoms") else ([] if shape.is_empty else [shape])


class Drawing:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.scale = 16
        self.image = Image.new("RGB", (round(width * self.scale), round(height * self.scale)), "#eef2f6")
        self.draw = ImageDraw.Draw(self.image)
        self.elements = [f'<rect width="{width}" height="{height}" fill="#eef2f6"/>']

    def text(self, x, y, value, size=2.3, color="#172433"):
        self.elements.append(f'<text x="{x}" y="{y}" font-family="sans-serif" font-size="{size}" fill="{color}">{escape(value)}</text>')
        font = ImageFont.load_default(size=round(size * self.scale))
        self.draw.text((x * self.scale, (y - size) * self.scale), value, fill=color, font=font)

    def line(self, points, color="#697b8e", width=.15):
        values = " ".join(f"{x:.4f},{y:.4f}" for x, y in points)
        self.elements.append(f'<polyline points="{values}" fill="none" stroke="{color}" stroke-width="{width}"/>')
        self.draw.line([(x * self.scale, y * self.scale) for x, y in points], fill=color, width=max(1, round(width * self.scale)))

    def face(self, face, x=0, y=0, factor=1, fill="#f7f6ee", holes="#171d28"):
        def convert(ring):
            return [(x + px * factor, y - py * factor) for px, py in ring]

        rings = [convert(face["outer"]), *[convert(ring) for ring in face["holes"]]]
        path = " ".join("M " + " L ".join(f"{px:.5f},{py:.5f}" for px, py in ring) + " Z" for ring in rings)
        self.elements.append(f'<path d="{path}" fill="{fill}" fill-rule="evenodd"/>')
        self.draw.polygon([(px * self.scale, py * self.scale) for px, py in rings[0]], fill=fill)
        for ring in rings[1:]:
            self.draw.polygon([(px * self.scale, py * self.scale) for px, py in ring], fill=holes)

    def rect(self, x, y, width, height, color):
        self.elements.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{color}"/>')
        self.draw.rectangle((x * self.scale, y * self.scale, (x + width) * self.scale, (y + height) * self.scale), fill=color)

    def save(self, stem):
        folder = PROPOSAL / "preview"
        folder.mkdir(exist_ok=True)
        (folder / f"{stem}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}mm" height="{self.height}mm" '
            f'viewBox="0 0 {self.width} {self.height}">'
            + "".join(self.elements) + "</svg>\n"
        )
        self.image.resize((round(self.width * 10), round(self.height * 10)), Image.Resampling.LANCZOS).save(folder / f"{stem}.png")


def main():
    actual = json.loads((WORK / "actual-native-preview.json").read_text())
    outlines = json.loads((WORK / "final-outlines.json").read_text())
    front = Drawing(162, 124)
    front.text(10, 7, "B NAMEPLATE / SAME TWO LINES / CANDIDATE ONLY", 3)
    for name, y, text in (
        ("current_top", 20, "CURRENT: rows 12 / 8 mm; white relief 0.8 mm"),
        ("candidate_top", 76, "CANDIDATE: rows 12 / 10 mm; white relief 1.2 mm"),
    ):
        front.text(10, y - 3, text)
        front.rect(10, y, 142, 40, "#171d28")
        for face in actual[name]:
            front.face(face, x=10, y=y + 40)
        front.line([(10, y + 42), (152, y + 42)])
        front.text(70, y + 46, "142 mm", 2.4)
    front.text(10, 123, "Native-derived ink at 1:1 in SVG; dark rectangle indicates carrier envelope. No photo or slicer preview.", 1.7)
    front.save("comparison-front")

    details = Drawing(172, 110)
    details.text(6, 7, "COUNTERS / e EXIT / ACTUAL CAD GLYPHS AT EQUAL SCALE", 2.8)
    for column, char in enumerate("aeod"):
        x = 6 + column * 42
        details.text(x, 13, char, 3)
        for version, y in (("current", 22), ("candidate", 66)):
            glyph = next(g for g in outlines[version][0]["glyphs"] if g["character"] == char)
            xs = [p[0] for f in glyph["faces"] for p in f["outer"]]
            ys = [p[1] for f in glyph["faces"] for p in f["outer"]]
            details.text(x, y - 2, version.upper(), 1.9)
            details.rect(x, y, 38, 36, "#171d28")
            for face in glyph["faces"]:
                details.face(face, x=x + 6 - min(xs) * 3, y=y + 33 + min(ys) * 3, factor=3)
    details.text(6, 109, "Ink contours x3; closed holes and the open e mouth are not interchangeable measurements.", 1.9)
    details.save("counter-detail")

    section = Drawing(112, 35)
    section.text(5, 5, "ACTUAL NATIVE SECTION / X = 71 mm / PRINT ORIENTATION", 2.1)
    for column, version in enumerate(("current", "candidate")):
        x, y = 6 + column * 55, 23
        section.text(x, 11, version.upper(), 2.4)
        for ring in actual[f"{version}_section_x71"]:
            shape = Polygon(ring)
            section.face({"outer": ring, "holes": []}, x=x, y=y, fill="#171d28")
            for raised in polygons(shape.intersection(box(-1, 2.4, 41, 5))):
                if raised.geom_type == "Polygon":
                    section.face({"outer": list(raised.exterior.coords),
                                  "holes": [list(h.coords) for h in raised.interiors]}, x=x, y=y)
        section.line([(x - 1, y), (x + 41, y)])
        section.text(x, 28, "BLACK 2.4 + WHITE " + ("0.8" if version == "current" else "1.2") + " mm", 1.9)
    section.text(5, 34, "Same scale on both axes. Only the white relief grows; carrier and color-change boundary stay unchanged.", 1.6)
    section.save("side-section")

    width, height, _ = actual["coupon_dimensions_mm"]
    coupon = Drawing(width + 12, height + 21)
    coupon.text(6, 6, "FULL-SCALE GLYPH COUPON / NOT A FIT TEST", 2.2)
    coupon.rect(6, 11, width, height, "#171d28")
    for face in actual["coupon_top"]:
        coupon.face(face, x=6, y=11 + height)
    coupon.text(6, height + 17, f"{width:g} x {height:g} x 3.6 mm; black2.4 + white1.2; scale100%", 1.9)
    coupon.save("coupon-front")
    print("Saved actual-native comparison, counter detail, section and coupon SVG/PNG.")


if __name__ == "__main__":
    main()
