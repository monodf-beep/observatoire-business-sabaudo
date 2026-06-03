#!/usr/bin/env python3
"""Génère les bannières de substitution par territoire (charte Cultura Sabauda).

Sobres, sans photo (donc aucun souci de droits), aux couleurs de la marque.
À téléverser ensuite dans Brevo (Bibliothèque de contenu) ; coller les URLs
obtenues dans config/territory_images.txt.

Usage : python scripts/make_banners.py [--dir DOSSIER]
Nécessite Pillow (déjà dans requirements) et une police TrueType (Liberation Sans).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

BRAND = (63, 95, 150)      # bleu Cultura Sabauda
ACCENT = (223, 102, 79)    # orange du point
EYE = (174, 203, 240)
SUB = (207, 224, 244)

TERRITORIES = {
    "savoie": ("Savoie", (26, 86, 176)),
    "piemonte": ("Piémont", (179, 38, 30)),
    "vallee-aoste": ("Vallée d'Aoste", (30, 125, 52)),
    "nice": ("Nice", (178, 94, 0)),
    "alcotra": ("Alcotra", (90, 58, 165)),
    "default": ("Espace Sabaudo", (223, 102, 79)),
}
W, H = 1200, 600


def make(key: str, label: str, accent: tuple, out_dir: Path) -> Path:
    im = Image.new("RGB", (W, H), BRAND)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 18, H], fill=accent)                 # bande territoire
    d.ellipse([W - 150, 70, W - 90, 130], fill=accent)      # pastille
    d.text((70, 80), "OBSERVATOIRE ÉCONOMIQUE", font=ImageFont.truetype(BOLD, 30), fill=EYE)
    size = 120
    while size > 40:
        f = ImageFont.truetype(BOLD, size)
        if d.textlength(label, font=f) <= W - 160:
            break
        size -= 4
    f = ImageFont.truetype(BOLD, size)
    d.text((68, 150), label, font=f, fill=(255, 255, 255))
    tw = d.textlength(label, font=f)
    dot_y = 150 + int(size * 0.62)
    d.ellipse([68 + tw + 14, dot_y, 68 + tw + 34, dot_y + 20], fill=ACCENT)
    d.text((70, H - 90), "Business Sabaudo", font=ImageFont.truetype(REG, 34), fill=SUB)
    out = out_dir / f"{key}.png"
    im.save(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Génère les bannières de territoire.")
    parser.add_argument("--dir", default="banners", help="Dossier de sortie.")
    args = parser.parse_args()
    out_dir = Path(args.dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, (label, accent) in TERRITORIES.items():
        print("écrit :", make(key, label, accent, out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
