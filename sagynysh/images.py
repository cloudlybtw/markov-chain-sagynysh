"""Demotivator and meme image rendering. Pure Pillow — no Telegram
dependency, so this stays unit-testable."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
DEMOTIVATOR_TITLE_FONT = FONTS_DIR / "PTSerif-Bold.ttf"
DEMOTIVATOR_SUBTITLE_FONT = FONTS_DIR / "PTSerif-Regular.ttf"
MEME_FONT = FONTS_DIR / "Oswald-Bold.ttf"

MAX_IMAGE_SIDE = 800
JPEG_QUALITY = 90

DEMOTIVATOR_MARGIN_RATIO = 0.08
DEMOTIVATOR_FRAME_WIDTH = 3
DEMOTIVATOR_FRAME_GAP = 5
DEMOTIVATOR_TITLE_SIZE = 54
DEMOTIVATOR_SUBTITLE_SIZE = 32
DEMOTIVATOR_MIN_FONT_SIZE = 14
DEMOTIVATOR_LINE_SPACING = 1.15

MEME_MARGIN_RATIO = 0.05
MEME_FONT_SIZE = 64
MEME_MIN_FONT_SIZE = 18
MEME_LINE_SPACING = 1.1


def render_demotivator(img: Image.Image, title: str, subtitle: str) -> bytes:
    photo = _scale_to_fit(img.convert("RGB"), MAX_IMAGE_SIDE)
    margin = max(
        round(photo.width * DEMOTIVATOR_MARGIN_RATIO),
        DEMOTIVATOR_FRAME_GAP + DEMOTIVATOR_FRAME_WIDTH + 2,
    )
    canvas_width = photo.width + margin * 2
    text_max_width = canvas_width - margin * 2

    measurer = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    title_font, title_lines = _fit_text(
        measurer, title.upper(), DEMOTIVATOR_TITLE_FONT, text_max_width, DEMOTIVATOR_TITLE_SIZE
    )
    subtitle_font, subtitle_lines = _fit_text(
        measurer, subtitle, DEMOTIVATOR_SUBTITLE_FONT, text_max_width, DEMOTIVATOR_SUBTITLE_SIZE
    )

    title_line_height = _line_height(title_font, DEMOTIVATOR_LINE_SPACING)
    subtitle_line_height = _line_height(subtitle_font, DEMOTIVATOR_LINE_SPACING)
    gap_before_subtitle = round(subtitle_line_height * 0.6)

    text_top = margin + photo.height + margin
    text_height = title_line_height * len(title_lines)
    if subtitle_lines:
        text_height += gap_before_subtitle + subtitle_line_height * len(subtitle_lines)
    canvas_height = text_top + text_height + margin

    canvas = Image.new("RGB", (canvas_width, canvas_height), "black")
    canvas.paste(photo, (margin, margin))

    draw = ImageDraw.Draw(canvas)
    frame_box = (
        margin - DEMOTIVATOR_FRAME_GAP,
        margin - DEMOTIVATOR_FRAME_GAP,
        margin + photo.width + DEMOTIVATOR_FRAME_GAP,
        margin + photo.height + DEMOTIVATOR_FRAME_GAP,
    )
    draw.rectangle(frame_box, outline="white", width=DEMOTIVATOR_FRAME_WIDTH)

    y = text_top
    for line in title_lines:
        _draw_centered_line(draw, line, title_font, canvas_width, y, fill="white")
        y += title_line_height
    if subtitle_lines:
        y += gap_before_subtitle
        for line in subtitle_lines:
            _draw_centered_line(draw, line, subtitle_font, canvas_width, y, fill="white")
            y += subtitle_line_height

    return _to_jpeg_bytes(canvas)


def render_meme(img: Image.Image, top: str, bottom: str) -> bytes:
    canvas = _scale_to_fit(img.convert("RGB"), MAX_IMAGE_SIDE).copy()
    draw = ImageDraw.Draw(canvas)
    max_width = round(canvas.width * (1 - 2 * MEME_MARGIN_RATIO))
    edge_padding = round(canvas.height * MEME_MARGIN_RATIO * 0.5)

    if top:
        font, lines = _fit_text(
            draw, top.upper(), MEME_FONT, max_width, MEME_FONT_SIZE, MEME_MIN_FONT_SIZE
        )
        _draw_meme_block(draw, lines, font, canvas.width, edge_padding)

    if bottom:
        font, lines = _fit_text(
            draw, bottom.upper(), MEME_FONT, max_width, MEME_FONT_SIZE, MEME_MIN_FONT_SIZE
        )
        line_height = _line_height(font, MEME_LINE_SPACING)
        y = canvas.height - edge_padding - line_height * len(lines)
        _draw_meme_block(draw, lines, font, canvas.width, y)

    return _to_jpeg_bytes(canvas)


def _draw_meme_block(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    canvas_width: int,
    y: int,
) -> None:
    stroke_width = max(1, font.size // 15)
    line_height = _line_height(font, MEME_LINE_SPACING)
    for line in lines:
        width = _measure(draw, line, font, stroke_width)
        x = (canvas_width - width) // 2
        draw.text(
            (x, y), line, font=font, fill="white", stroke_width=stroke_width, stroke_fill="black"
        )
        y += line_height


def _scale_to_fit(img: Image.Image, max_side: int) -> Image.Image:
    longest = max(img.width, img.height)
    if longest <= max_side:
        return img
    scale = max_side / longest
    new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _measure(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, stroke_width: int = 0
) -> int:
    if not text:
        return 0
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return bbox[2] - bbox[0]


def _line_height(font: ImageFont.FreeTypeFont, spacing: float) -> int:
    return round(sum(font.getmetrics()) * spacing)


def _wrap_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    stroke_width: int = 0,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if not current or _measure(draw, candidate, font, stroke_width) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: Path,
    max_width: int,
    start_size: int,
    min_size: int = 10,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    size = start_size
    while True:
        font = ImageFont.truetype(str(font_path), size)
        stroke_width = max(1, size // 15) if font_path == MEME_FONT else 0
        lines = _wrap_lines(draw, text, font, max_width, stroke_width)
        widest = max((_measure(draw, line, font, stroke_width) for line in lines), default=0)
        if widest <= max_width or size <= min_size:
            return font, lines
        size -= 2


def _draw_centered_line(
    draw: ImageDraw.ImageDraw,
    line: str,
    font: ImageFont.FreeTypeFont,
    canvas_width: int,
    y: int,
    fill: str,
) -> None:
    width = _measure(draw, line, font)
    x = (canvas_width - width) // 2
    draw.text((x, y), line, font=font, fill=fill)


def _to_jpeg_bytes(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()
