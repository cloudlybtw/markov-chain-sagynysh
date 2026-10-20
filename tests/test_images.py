import io

import pytest
from PIL import Image, ImageFont

from sagynysh import images

JPEG_MAGIC = b"\xff\xd8"

SIZES = [
    (5, 5),  # tiny
    (2000, 1500),  # huge
    (300, 900),  # non-square, tall
    (900, 300),  # non-square, wide
]


def _make_image(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), (120, 160, 200))


@pytest.mark.parametrize("width,height", SIZES)
def test_render_demotivator_returns_valid_jpeg(width, height):
    img = _make_image(width, height)
    data = images.render_demotivator(img, "заголовок дня", "подзаголовок покороче тоже")

    assert data[:2] == JPEG_MAGIC
    result = Image.open(io.BytesIO(data))
    result.load()
    assert result.format == "JPEG"


@pytest.mark.parametrize("width,height", SIZES)
def test_render_meme_returns_valid_jpeg(width, height):
    img = _make_image(width, height)
    data = images.render_meme(img, "верхний текст", "нижний текст")

    assert data[:2] == JPEG_MAGIC
    result = Image.open(io.BytesIO(data))
    result.load()
    assert result.format == "JPEG"


def test_render_demotivator_handles_empty_subtitle():
    data = images.render_demotivator(_make_image(400, 300), "только заголовок", "")
    Image.open(io.BytesIO(data)).load()


def test_render_meme_handles_missing_bottom_text():
    data = images.render_meme(_make_image(400, 300), "верх", "")
    Image.open(io.BytesIO(data)).load()


def test_render_meme_handles_missing_top_text():
    data = images.render_meme(_make_image(400, 300), "", "низ")
    Image.open(io.BytesIO(data)).load()


def test_render_demotivator_wraps_long_text_without_crashing():
    long_title = " ".join(["слово"] * 20)
    data = images.render_demotivator(_make_image(400, 300), long_title, long_title)
    Image.open(io.BytesIO(data)).load()


def test_scale_to_fit_caps_longest_side():
    scaled = images._scale_to_fit(_make_image(2000, 1000), 800)
    assert scaled.size == (800, 400)


def test_scale_to_fit_leaves_small_images_unscaled():
    scaled = images._scale_to_fit(_make_image(100, 50), 800)
    assert scaled.size == (100, 50)


@pytest.mark.parametrize(
    "font_path",
    [images.DEMOTIVATOR_TITLE_FONT, images.DEMOTIVATOR_SUBTITLE_FONT, images.MEME_FONT],
)
def test_fonts_render_cyrillic_and_kazakh_without_tofu(font_path):
    font = ImageFont.truetype(str(font_path), 40)
    chars = "привет мир" + "әғқңөұүһі" + "ӘҒҚҢӨҰҮҺІ"
    for ch in chars:
        if ch == " ":
            continue
        mask = font.getmask(ch)
        assert mask.getbbox() is not None, f"missing glyph for {ch!r} in {font_path}"
