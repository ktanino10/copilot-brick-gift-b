"""Update only affected real CAD projections and reassemble the existing 54-page PDF."""

from html import escape
import base64
import io
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from reportlab.pdfgen import canvas
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".work/plate-v2"
SVG = "{http://www.w3.org/2000/svg}"


def text(x, y, value, size=17, color="#172433"):
    return f'<text x="{x}" y="{y}" font-family="Helvetica,Arial,sans-serif" font-size="{size}" fill="{color}">{escape(value)}</text>'


def page(title, content, subtitle="Actual current FreeCAD geometry; NOT_SLICED / physical fit and print quality unverified."):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297.5mm" viewBox="0 0 1200 850">'
        '<rect width="1200" height="850" fill="white"/>'
        + text(42, 42, "PRIVATE B / 4.1-B-legibility.1 / TWO-LINE NAMEPLATE", 13)
        + text(42, 80, title, 27) + text(42, 109, subtitle, 13)
        + '<path d="M42 127 H1158 M42 801 H1158" stroke="#ccd5de"/>'
        + content + text(42, 826, "UNITS mm | STL100% | Black support2.4; white letters1.2; add Pause before white paths.", 12)
        + "</svg>\n"
    )


def projection(data, x, baseline, scale):
    return f'<g transform="translate({x},{baseline}) scale({scale})">{data["svg"]}</g>'


def image(name, x, y, width, height):
    encoded = base64.b64encode((ROOT / "docs/images" / name).read_bytes()).decode()
    return (f'<image xmlns:xlink="http://www.w3.org/1999/xlink" x="{x}" y="{y}" width="{width}" '
            f'height="{height}" preserveAspectRatio="xMidYMid meet" xlink:href="data:image/png;base64,{encoded}"/>')


def save(relative, title, content, subtitle=None):
    (ROOT / relative).write_text(page(title, content, **({"subtitle": subtitle} if subtitle else {})))


def section_lines(lines, x, baseline, scale, clip=None):
    body = []
    for line in lines:
        color = "#1680ae" if line["part"] == "NP3-TEXT-B" else "#172433"
        points = " ".join(f"{x + a * scale:.5f},{baseline - b * scale:.5f}" for a, b in line["points"])
        body.append(f'<polyline points="{points}" stroke="{color}" stroke-width="1" fill="none"/>')
    content = "".join(body)
    return f'<g clip-path="url(#{clip})">{content}</g>' if clip else content


def main():
    data = json.loads((WORK / "production-projections.json").read_text())
    save("kit/B/drawings/overview.svg", "B / DESK CLASSIC / CURRENT ENVELOPE",
         text(70, 175, "FRONT / nameplate side")
         + image("B-overview-front.png", 60, 200, 430, 515)
         + text(180, 748, "191.8 W / 238.6 H")
         + text(570, 175, "RIGHT SIDE")
         + image("B-overview-right.png", 520, 200, 260, 515)
         + text(575, 748, "80.2 total depth")
         + text(805, 175, "TOP / front at bottom")
         + image("B-overview-top.png", 805, 210, 340, 210)
         + text(805, 485, "150 assembled parts", 20)
         + text(805, 520, "28 steps / 5 base courses")
         + text(805, 555, "Base footprint:191.8 x79.8", 15)
         + text(805, 585, "Base body height:48", 15)
         + text(805, 620, "White letters project0.4 farther", 15)
         + text(805, 650, "forward; all150 placements", 15)
         + text(805, 677, "and20 non-text masters unchanged.", 15)
         + text(805, 710, "Orange outline: selection aid only.", 14),
         "Slightly elevated orthographic STL views; dimension labels are native values. Not a photo or a fit certification.")
    save("kit/B/drawings/exploded.svg", "B / FRONT MODULE INSERTION AND RELEASE REFERENCE",
         image("B-front-release.png", 60, 235, 465, 465)
         + text(550, 178, "Current STL; explanatory motion only.", 20)
         + text(550, 211, "Not a physical release simulation or a measured height.")
         + text(550, 247, "Release text keepers first: up6, forward32, then aside.")
         + text(550, 278, "Lift the independent nameplate45, then forward.")
         + text(550, 306, "Blue ghost: destination, NOT a second plate.", 15)
         + text(550, 328, "CURRENT NAMEPLATE / FLAT PRINT VIEW")
         + projection(data["plate_top"], 570, 503, 3.7)
         + text(550, 557, "Same icon, New adventures")
         + text(550, 590, "github.com/tomokota")
         + text(550, 633, "Black2.4 + white1.2 =3.6; rows12 /10 mm")
         + text(550, 682, "Use the offline guide for all28 steps /150 parts."),
         "Left: current mesh insertion detail; right: actual native plate cap contours. Not a force simulation.")
    save("kit/B/drawings/parts/NP3-TEXT-B.svg", "NP3-TEXT-B / LEGIBILITY V2",
         text(75, 177, "TOP / REAR ON BED / LETTERS UP")
         + projection(data["plate_top"], 75, 382, 4.1)
         + text(275, 418, "142.00 x40.00")
         + text(75, 485, "NATIVE SECTION Y=26 / TOTAL3.60")
         + projection(data["plate_front"], 75, 540, 4.1)
         + text(760, 485, "SECTION X=71 /40.00 x3.60")
         + projection(data["plate_right"], 775, 540, 4.1)
         + text(75, 593, "Unchanged black carrier:142 x40 x2.4; keyed rear geometry preserved.")
         + text(75, 628, "Actual ink row heights12 /10; white relief1.2; black-to-white after2.4.")
         + text(75, 663, "Same icon, New adventures")
         + text(75, 696, "github.com/tomokota")
         + text(75, 749, "Print the lettering coupon first. Thickness does not diagnose stringing or surface roughness.", 15))

    save("kit/fit/front-interface.svg", "B / CURRENT FRONT INTERFACE AND RELEASE",
         '<defs><clipPath id="frontband"><rect x="55" y="237" width="1090" height="80"/></clipPath></defs>'
         + text(65, 177, "HORIZONTAL SECTION Z=24 / FRONT8mm BAND / BLUE: CURRENT NAMEPLATE")
         + section_lines(data["front_section_z24"], 70, 300, 5, "frontband")
         + text(65, 370, "VERTICAL SECTION X=40 / Y-Z PLANE")
         + section_lines(data["front_section_x40"], 75, 705, 5)
         + text(600, 450, "Black carrier2.40 / rear flat0.80", 18)
         + text(600, 489, "Side taper2.00; receiver clearance unchanged.")
         + text(600, 529, "Text face Y=-0.30; logo face Y=0.10.")
         + text(600, 569, "Carrier fit remains inside the original keyed slide.")
         + text(600, 609, "Two text keepers: up6, forward32, then aside.")
         + text(600, 649, "Nameplate: lift45, then forward14.")
         + text(600, 689, "Digital swept envelopes: no intersections.")
         + text(600, 729, "Physical clutch / force / retention not certified.", 15))

    changed_steps = []
    for number in range(6, 29):
        path = ROOT / f"kit/B/drawings/step-{number:02}.svg"
        root = ET.parse(path).getroot()
        count = 0
        for node in root.iter(SVG + "rect"):
            if all(abs(float(node.get(key, "-1")) - expected) < 1e-6 for key, expected in (
                ("x", 88.54166666666667), ("width", 480.72916666666663),
            )) and any(abs(float(node.get("height", "-1")) - height) < 1e-6
                       for height in (10.833333333333334, 12.1875)):
                node.set("height", "12.1875")
                count += 1
        if count != 1:
            raise ValueError(f"Expected exactly one old nameplate footprint in step{number}, got{count}.")
        for node in root.iter(SVG + "text"):
            if node.text and " / REV3 / " in node.text:
                node.text = node.text.replace(" / REV3 / ", " / LEGIBILITY4.1 / ")
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        path.write_text(ET.tostring(root, encoding="unicode") + "\n")
        changed_steps.append(number)

    drawings = ROOT / "kit/B/drawings"
    files = [
        drawings / "overview.svg", drawings / "exploded.svg",
        ROOT / "kit/fit/interface.svg", ROOT / "kit/fit/front-interface.svg",
        drawings / "bom-1.svg",
        *[drawings / f"step-{number:02}.svg" for number in range(1, 29)],
        *sorted((drawings / "parts").glob("*.svg")),
    ]
    if len(files) != 54:
        raise ValueError("The existing B drawing inventory must remain54 pages.")
    output = ROOT / "kit/B/drawings.pdf"
    document = canvas.Canvas(str(output), pagesize=(840, 595), pageCompression=1)
    document.setTitle("Private B legibility-v2 drawings")
    document.setAuthor("Copilot Brick Display contributors")
    for path in files:
        drawing = svg2rlg(io.BytesIO(path.read_bytes()))
        if drawing is None:
            raise ValueError(f"Cannot render SVG: {path.name}")
        factor = min(840 / drawing.width, 595 / drawing.height)
        document.saveState()
        document.scale(factor, factor)
        renderPDF.draw(drawing, document, 0, 0)
        document.restoreState()
        document.showPage()
    document.save()
    for source, destination in (
        ("comparison-front.png", "nameplate-v2-comparison.png"),
        ("counter-detail.png", "nameplate-v2-counters.png"),
        ("side-section.png", "nameplate-v2-section.png"),
        ("coupon-front.png", "nameplate-v2-coupon.png"),
    ):
        shutil.copyfile(ROOT / "proposals/plate-legibility-v2/preview" / source,
                        ROOT / "docs/images" / destination)
    front = ROOT / "docs/images/nameplate-front.svg"
    front.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="142mm" height="40mm" viewBox="0 -40 142 40">'
        + data["plate_top"]["svg"] + "</svg>\n"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser_page = browser.new_context(viewport={"width": 1420, "height": 400}, offline=True).new_page()
        browser_page.goto(front.as_uri())
        browser_page.locator("svg").evaluate(
            "svg => {svg.style.width='100vw';svg.style.height='100vh';document.body?.style.setProperty('margin','0')}"
        )
        browser_page.locator("svg").screenshot(path=str(ROOT / "docs/images/nameplate-front.png"))
        browser.close()
    print(f"Updated only affected CAD projections/plate footprints; assembled{len(files)} PDF pages. Steps:{changed_steps}")


if __name__ == "__main__":
    main()
