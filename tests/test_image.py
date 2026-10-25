"""Обрезка по листу на синтетических картинках: белый лист под углом на тёмном столе."""

import io

import cv2
import numpy as np
from PIL import Image

from naryad.image import MAX_SIDE, find_sheet, prepare, warp

SHEET = np.array([[300, 150], [1100, 250], [1000, 1150], [200, 1000]], dtype=np.float32)  # tl, tr, br, bl


def photo(sheet: np.ndarray | None = SHEET) -> Image.Image:
    img = np.full((1300, 1400, 3), (90, 110, 140), np.uint8)  # «деревянный» стол
    if sheet is not None:
        cv2.fillPoly(img, [sheet.astype(np.int32)], (245, 245, 245))
        cv2.putText(img, "NARYAD 107", (380, 500), cv2.FONT_HERSHEY_SIMPLEX, 2, (20, 20, 20), 4)
    return Image.fromarray(img)


def test_finds_corners_of_tilted_sheet():
    corners = find_sheet(photo())
    assert corners is not None
    assert np.abs(corners - SHEET).max() < 15  # пикселей исходного фото


def test_no_sheet_returns_none():
    assert find_sheet(photo(sheet=None)) is None


def test_warp_produces_upright_rectangle():
    out = warp(photo(), SHEET)
    w, h = out.size
    assert 780 < w < 830 and 880 < h < 920  # длины сторон листа


def test_prepare_falls_back_to_full_frame(tmp_path):
    path = tmp_path / "empty.jpg"
    photo(sheet=None).save(path)
    result = prepare(path)
    assert result.cropped is False
    assert max(Image.open(io.BytesIO(result.jpeg)).size) <= MAX_SIDE


def test_prepare_respects_exif_rotation(tmp_path):
    path = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: повернуть на 90° — так пишет телефон, снятый вертикально
    Image.new("RGB", (400, 200), "white").save(path, exif=exif)
    w, h = Image.open(io.BytesIO(prepare(path, crop=False).jpeg)).size
    assert h > w
