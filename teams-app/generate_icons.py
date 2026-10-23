"""Generate Teams app icons (POC-17).

color.png   — 192x192, full colour (shown in Teams app store and install dialog)
outline.png — 32x32, white on transparent (used in Teams sidebar/header)

Teams rules:
  - color:   exactly 192x192, PNG, <= 100 KB, any colour
  - outline: exactly 32x32,   PNG, white + transparent only
"""

from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).parent


def make_color_icon() -> None:
    size = 192
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle — Teams blue
    margin = 6
    draw.ellipse([margin, margin, size - margin, size - margin], fill="#0078D4")

    # Outer ring accent
    draw.ellipse([margin, margin, size - margin, size - margin],
                 outline="#005A9E", width=4)

    # Stand-up "S" shape: three horizontal bars (simple scrum symbol)
    bar_color = "#FFFFFF"
    cx = size // 2
    bar_w = 80
    bar_h = 12
    gap = 18

    # top bar
    draw.rounded_rectangle(
        [cx - bar_w // 2, 64, cx + bar_w // 2, 64 + bar_h],
        radius=6, fill=bar_color
    )
    # middle bar (shorter — arrow hint)
    draw.rounded_rectangle(
        [cx - bar_w // 2, 64 + bar_h + gap, cx + bar_w // 2 - 20, 64 + bar_h * 2 + gap],
        radius=6, fill=bar_color
    )
    # bottom bar
    draw.rounded_rectangle(
        [cx - bar_w // 2, 64 + bar_h * 2 + gap * 2, cx + bar_w // 2, 64 + bar_h * 3 + gap * 2],
        radius=6, fill=bar_color
    )

    # Small circle — "person" dot above bars
    draw.ellipse([cx - 14, 28, cx + 14, 56], fill=bar_color)

    img.save(OUT / "color.png", "PNG", optimize=True)
    print(f"wrote color.png  ({(OUT / 'color.png').stat().st_size // 1024} KB)")


def make_outline_icon() -> None:
    size = 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    white = (255, 255, 255, 255)

    # Person head
    draw.ellipse([12, 2, 20, 10], fill=white)

    # Three bars (scrum list)
    draw.rounded_rectangle([4, 13, 28, 16], radius=2, fill=white)
    draw.rounded_rectangle([4, 19, 24, 22], radius=2, fill=white)
    draw.rounded_rectangle([4, 25, 28, 28], radius=2, fill=white)

    img.save(OUT / "outline.png", "PNG", optimize=True)
    print(f"wrote outline.png  ({(OUT / 'outline.png').stat().st_size} bytes)")


if __name__ == "__main__":
    make_color_icon()
    make_outline_icon()
    print("done — validate with: make manifest && upload teams-app/scrum-bot.zip to dev.teams.microsoft.com/apps")
