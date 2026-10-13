"""Export the six complete tables read from the live Orbea geometry controls."""
import json
from pathlib import Path
import re
import zipfile

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).parent
source = json.loads((ROOT / "verified-tables.json").read_text(encoding="utf-8"))


def font(size, bold=False):
    return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)


exports = []
for variant in source["variants"]:
    name = "geometry-" + "-".join(re.sub(r"[^a-z0-9]+", "-", f"{setting['label']}-{setting['text']}".lower()).strip("-")
                                   for setting in variant["settings"]) + ".png"
    width, padding, row_height = 720, 24, 40
    table_top = 132
    height = table_top + 44 + row_height * len(variant["rows"]) + 60
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((padding, 20), "OCCAM LT M10 — Geometry", font=font(22, True), fill="#161616")
    for index, setting in enumerate(variant["settings"]):
        draw.text((padding, 60 + index * 28), f"{setting['label']}: {setting['text']}", font=font(18), fill="#161616")
    label_width = 336
    cell_width = (width - padding * 2 - label_width) / (len(variant["headers"]) - 1)

    def cells(values, top, header=False):
        current_font = font(18, header)
        colour = "#555555" if header else "#161616"
        for column, value in enumerate(values):
            x = padding if column == 0 else padding + label_width + column * cell_width - current_font.getlength(value) - 8
            draw.text((x, top + 11), value, font=current_font, fill=colour)

    cells(variant["headers"], table_top, True)
    draw.line((padding, table_top + 43, width - padding, table_top + 43), fill="#aaaaaa")
    for index, row in enumerate(variant["rows"]):
        top = table_top + 44 + index * row_height
        cells(row, top)
        draw.line((padding, top + row_height - 1, width - padding, top + row_height - 1), fill="#dddddd")
    draw.text((padding, height - 32), "Source: orbea.com/en-be/occam-lt-m10", font=font(13), fill="#555555")
    image.save(ROOT / name, "PNG", optimize=True)
    exports.append({"filename": name, **variant})

manifest = {"source": source["source"], "capture": "All six live native-select configurations; complete S/M/L/XL table values rendered as labelled PNGs.",
            "variants": exports}
(ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
with zipfile.ZipFile(ROOT / "occam-lt-m10-all-geometry.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for item in exports:
        archive.write(ROOT / item["filename"], item["filename"])
    archive.write(ROOT / "manifest.json", "manifest.json")
print(f"Exported {len(exports)} verified geometry PNGs")
