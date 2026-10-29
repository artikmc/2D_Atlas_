"""Детекция кадров спрайт-атласов по альфа-каналу.

Формат: горизонтальные ряды поз, прозрачный фон (RGBA).
Требует только PIL — numpy не нужен.
"""
from PIL import Image


def _bands(flags, min_len=1):
    """Участки подряд идущих True: [(start, end), ...] включительно."""
    out, start = [], None
    for i, v in enumerate(flags):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                out.append((start, i - 1))
            start = None
    if start is not None and len(flags) - start >= min_len:
        out.append((start, len(flags) - 1))
    return out


def _merge_close(intervals, min_gap):
    """Сливает интервалы, разделённые зазором меньше min_gap (часть тела)."""
    merged = []
    for x0, x1 in intervals:
        if merged and x0 - merged[-1][1] - 1 < min_gap:
            merged[-1][1] = max(merged[-1][1], x1)
        else:
            merged.append([x0, x1])
    return [(m[0], m[1]) for m in merged]


def detect_frames(image, alpha_threshold=8, min_row_height=3, min_gap=4):
    """Ищет ряды и кадры в них по альфа-каналу.

    :param image: PIL.Image (RGBA с прозрачностью; залитый фон не детектится)
    :param alpha_threshold: минимальная непрозрачность, чтобы пиксель считался содержимым
    :param min_row_height: минимальная высота ряда в пикселях (шум фильтр)
    :param min_gap: зазоры между группами пикселей меньше этого — сливаются в один кадр
    :return: {"rows": [{"y0": int, "y1": int, "frames": [(x0, x1), ...]}, ...]}
             координаты внутри переданного изображения; y1/x1 включительно.
             {"rows": []} — если детектировать нечего (нет прозрачности или мусор).
    """
    rgba = image.convert("RGBA")
    w, h = rgba.size
    alpha = rgba.getchannel("A")

    # Картинка целиком непрозрачная (залитый фон) — резать по альфа нельзя.
    lo, hi = alpha.getextrema()
    if lo > alpha_threshold:
        return {"rows": []}

    # 1) Ряды: строки, где есть хоть один «засвеченный» пиксель.
    row_flags = []
    for y in range(h):
        ext = alpha.crop((0, y, w, y + 1)).getextrema()
        row_flags.append(ext is not None and ext[1] > alpha_threshold)

    rows = []
    # 2) Кадры внутри каждого ряда: столбцы с содержимым, зазоры < min_gap сливаем.
    for (y0, y1) in _bands(row_flags, min_len=min_row_height):
        col_flags = []
        for x in range(w):
            ext = alpha.crop((x, y0, x + 1, y1 + 1)).getextrema()
            col_flags.append(ext is not None and ext[1] > alpha_threshold)
        frames = _merge_close(_bands(col_flags, min_len=1), min_gap)
        if frames:
            rows.append({"y0": y0, "y1": y1, "frames": frames})

    return {"rows": rows}
