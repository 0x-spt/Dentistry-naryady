"""Подготовка фото перед отправкой модели.

Конвейер: поворот по EXIF → поиск листа → выравнивание перспективы → уменьшение → JPEG.

Зачем обрезка: модель получает картинку не больше MAX_SIDE по длинной стороне.
Если лист занимает треть кадра, на текст приходится треть пикселей, и «7» читается как «3».
После обрезки весь бюджет пикселей уходит на лист, а перспектива выпрямляется.
"""

import io
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

# Меняй при любой правке, влияющей на итоговую картинку: версия входит в ключ кэша ответов
PREPROCESS_VERSION = "2"

MAX_SIDE = 1568  # px по длинной стороне картинки для модели
JPEG_QUALITY = 90
DETECT_SIDE = 1000  # лист ищем на уменьшенной копии: быстрее и меньше шума от текстуры стола
MIN_SHEET_SHARE = 0.15  # контур меньше 15% кадра — скорее блик или салфетка, а не лист
MAX_SHEET_SHARE = 0.98  # контур почти во весь кадр — значит, лист и так заполняет снимок


@dataclass(frozen=True)
class Prepared:
    jpeg: bytes
    cropped: bool  # нашёлся ли лист; если нет — отправляем кадр целиком


def load(path: Path) -> Image.Image:
    """Открывает фото с учётом поворота: телефон хранит его в EXIF, а не в пикселях."""
    with Image.open(path) as img:
        return ImageOps.exif_transpose(img).convert("RGB")


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Упорядочивает 4 точки: левый верх, правый верх, правый низ, левый низ."""
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], dtype=np.float32)


def find_sheet(img: Image.Image) -> np.ndarray | None:
    """Углы листа в координатах исходного фото или None, если лист не найден."""
    scale = DETECT_SIDE / max(img.size)
    small = img.resize((round(img.width * scale), round(img.height * scale)))
    gray = cv2.GaussianBlur(cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2GRAY), (5, 5), 0)

    # Лист — самая светлая большая область. Otsu сам выбирает порог между листом и фоном,
    # закрытие заливает тёмный текст внутри листа, чтобы контур был сплошным
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    sheet = cv2.convexHull(max(contours, key=cv2.contourArea))
    share = cv2.contourArea(sheet) / mask.size
    if not MIN_SHEET_SHARE <= share <= MAX_SHEET_SHARE:
        return None

    approx = cv2.approxPolyDP(sheet, 0.02 * cv2.arcLength(sheet, True), True)
    # 4 угла — обычный лист; иначе (сгиб, загнутый угол) — описанный прямоугольник
    quad = approx.reshape(-1, 2) if len(approx) == 4 else cv2.boxPoints(cv2.minAreaRect(sheet))
    return order_corners(quad.astype(np.float32) / scale)


def warp(img: Image.Image, corners: np.ndarray) -> Image.Image:
    """Вырезает лист и выпрямляет перспективу: снятый под углом лист становится прямоугольником."""
    tl, tr, br, bl = corners
    width = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    height = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(corners, target)
    return Image.fromarray(cv2.warpPerspective(np.asarray(img), matrix, (width, height)))


def to_jpeg(img: Image.Image) -> bytes:
    img = img.copy()
    img.thumbnail((MAX_SIDE, MAX_SIDE))  # сохраняет пропорции, только уменьшает
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def prepare(path: Path, crop: bool = True) -> Prepared:
    img = load(path)
    corners = find_sheet(img) if crop else None
    if corners is not None:
        img = warp(img, corners)
    return Prepared(jpeg=to_jpeg(img), cropped=corners is not None)
