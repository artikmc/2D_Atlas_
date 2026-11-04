# -*- coding: utf-8 -*-
"""Логика «ИИ-генерации кадров»: референс, промпты, вырезание фона, база, атлас.

Здесь нет GUI — как в dataset_export.py и lora_train.py. Окно (generate_window.py)
только собирает поля и печатает лог.

Главное ограничение проекта: torch/diffusers стоят только в venv kohya_ss,
а GUI работает на системном Python. Поэтому генерация — отдельный процесс
(sd_generate.py), а всё остальное (PIL, sqlite3) делается здесь.

Про фон (проверено на export_final/man18/man18_running_0001.png):
    alpha ровно бинарная {0,255}, а RGB под прозрачными пикселями = (0,0,0).
То есть kohya при обучении видела спрайт на ЧЁРНОМ фоне, а не на белом.
Отсюда две вещи:
    1) референс переводим в RGB — прозрачность сама станет чёрной, как при обучении;
    2) у сгенерированных кадров вырезаем чёрный фон, а не белый.
"""

import json
import os
import re
import sqlite3
import subprocess
import time
from io import BytesIO

from PIL import Image

# --- служебный класс: кадр-оригинал, из которого нарезали анимации -----------
MAIN_FRAME_CLASS = "основной кадр"

# --- перевод класса-позы в английское слово для промпта ----------------------
# словарь повторяет dataset_export.RU_TO_EN_POSE: промпт генерации и caption
# обучения должны называть позу одинаково, иначе LoRA не поймёт запрос
RU_TO_EN_POSE = {
    "стояние": "standing",
    "ходьба": "walking",
    "бег": "running",
    "прыжок": "jumping",
    "прыжок в верх": "jump_up",
    "прыжок вверх": "jump_up",
    "падение": "falling",
    "смерть": "death",
    "бросок": "throwing",
    "атака": "attack",
    "удар": "hit",
    "idle": "standing",
}

# --- теги стиля: те же, что в caption датасета ------------------------------
STYLE_TAGS = "pixel art, sprite, transparent background"

# --- что просим НЕ рисовать -------------------------------------------------
DEFAULT_NEGATIVE = ("blurry, photo, 3d render, realistic, shading, gradient, "
                    "text, watermark, frame, border, background scene")


# ===========================================================================
#  База данных
# ===========================================================================
def connect(db_path):
    """Соединение с базой или понятная ошибка (окно покажет её в логе)."""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"база не найдена: {os.path.abspath(db_path)}")
    return sqlite3.connect(db_path)


def table_columns(conn, table):
    """Имена колонок таблицы — база проекта бывает в двух версиях."""
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def list_characters(db_path):
    """[(id, name)] персонажей. Пустой список, если таблицы characters нет."""
    conn = connect(db_path)
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                            "AND name='characters'").fetchone():
            return []
        return [(r[0], r[1]) for r in
                conn.execute("SELECT id, name FROM characters ORDER BY name")]
    finally:
        conn.close()


def list_pose_classes(db_path, character_id=None):
    """Классы поз из базы, без служебного «основной кадр».

    Регистр в базе плавает («Стояние» и «стояние» — разные строки), поэтому
    схлопываем по lower() и берём написание, которое встречается чаще.
    """
    conn = connect(db_path)
    try:
        if character_id is None:
            rows = conn.execute(
                "SELECT class_name, COUNT(*) FROM frames WHERE class_name != ? "
                "GROUP BY class_name", (MAIN_FRAME_CLASS,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT class_name, COUNT(*) FROM frames WHERE class_name != ? "
                "AND character_id = ? GROUP BY class_name",
                (MAIN_FRAME_CLASS, character_id)).fetchall()
    finally:
        conn.close()

    agg = {}
    for name, n in rows:
        if not name:
            continue
        key = name.strip().lower()
        if key == MAIN_FRAME_CLASS.lower():
            continue
        cur = agg.get(key)
        if cur is None or n > cur[1]:
            agg[key] = (name.strip(), n)

    # порядок — как в RU_TO_EN_POSE (он задаёт логичный порядок анимаций),
    # затем всё остальное по алфавиту
    order = {k: i for i, k in enumerate(RU_TO_EN_POSE)}
    return [v[0] for k, v in sorted(
        agg.items(), key=lambda kv: (order.get(kv[0], 999), kv[0]))]


def pose_word(class_name):
    """Русский класс -> английское слово для промпта."""
    key = (class_name or "").strip().lower()
    if key in RU_TO_EN_POSE:
        return RU_TO_EN_POSE[key]
    return re.sub(r"\s+", "_", key) or "pose"


def transliterate(text):
    """Кириллица -> латиница. Таблица повторяет dataset_export.transliterate:
    триггер в промпте обязан совпасть с триггером, на котором учили LoRA.
    """
    mapping = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    return "".join(mapping.get(ch, ch) for ch in (text or "").lower())


def get_main_frame_id(conn, character_id):
    """id главного кадра персонажа — к нему привязываются кадры анимаций."""
    row = conn.execute(
        "SELECT id FROM frames WHERE class_name = ? AND character_id = ? "
        "ORDER BY id LIMIT 1", (MAIN_FRAME_CLASS, character_id)).fetchone()
    return row[0] if row else None


def get_reference_frame(conn, character_id):
    """Кадр-эталон персонажа из базы (PIL.Image) или None."""
    row = conn.execute(
        "SELECT frame_data FROM frames WHERE class_name = ? AND character_id = ? "
        "ORDER BY id LIMIT 1", (MAIN_FRAME_CLASS, character_id)).fetchone()
    if not row:
        return None
    return Image.open(BytesIO(row[0])).convert("RGBA")


def sprite_size_of_character(conn, character_id):
    """Типичный размер спрайта персонажа — (ширина, высота).

    Кадры в базе разного размера (22x45, 23x45, 28x45...). Для атласа нужна
    одна клетка, поэтому берём медианные ширину и высоту по кадрам классов
    этого персонажа. Без кадров — (32, 32).
    """
    rows = conn.execute(
        "SELECT frame_data FROM frames WHERE class_name != ? AND character_id = ?",
        (MAIN_FRAME_CLASS, character_id)).fetchall()
    if not rows:
        return (32, 32)
    ws, hs = [], []
    for (blob,) in rows:
        try:
            w, h = Image.open(BytesIO(blob)).size
        except Exception:
            continue
        ws.append(w)
        hs.append(h)
    if not ws:
        return (32, 32)

    def med(v):
        v = sorted(v)
        return v[len(v) // 2]

    return (med(ws), med(hs))


# ===========================================================================
#  Референс и промпты
# ===========================================================================
def prepare_reference(src_path, size=512, pad_color=(0, 0, 0)):
    """Готовит референс для img2img: квадрат с чёрным фоном, спрайт по центру.

    Почему чёрный: при обучении прозрачность превращалась в чёрный (RGB под
    alpha = 0). Модель ждёт именно такой контекст, иначе начнёт рисовать фон.

    :return: PIL.Image RGB size x size
    """
    img = Image.open(src_path)
    img = img.convert("RGBA")

    # обрезаем прозрачные поля: спрайт должен занимать кадр, а не висеть точкой
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)

    w, h = img.size
    if w == 0 or h == 0:
        raise ValueError("пустой референс")

    # вписываем в квадрат с полями 8%, пропорции сохраняем
    inner = int(size * 0.92)
    scale = min(inner / w, inner / h)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    # NEAREST, а не LANCZOS: спрайт пиксельный, сглаживание убивает пиксели
    resized = img.resize((nw, nh), Image.NEAREST)

    canvas = Image.new("RGB", (size, size), pad_color)
    # alpha ресайзим вместе с картинкой — края останутся резкими
    canvas.paste(resized, ((size - nw) // 2, (size - nh) // 2), resized)
    return canvas


def build_prompt(trigger, class_name, extra=""):
    """Промпт кадра: триггер + поза + стиль. Порядок как в caption обучения."""
    parts = [trigger, pose_word(class_name), STYLE_TAGS]
    if extra.strip():
        parts.append(extra.strip())
    return ", ".join(p for p in parts if p)


# ===========================================================================
#  Вырезание фона из сгенерированного кадра
# ===========================================================================
def cut_background(img, tolerance=38, feather=True):
    """Чёрный фон -> прозрачность. Возвращает RGBA.

    Считаем фоном не «всё тёмное», а только то, что связано с краями кадра:
    заливка от рамки по похожим пикселям. Иначе тёмные пиксели внутри спрайта
    (обувь, волосы) стали бы дырками.

    Дальше альфа бинаризуется (0 или 255), как в исходных кадрах базы: там
    alpha ровно {0,255}.

    :param tolerance: насколько пиксель может отличаться от фона и всё ещё считаться фоном
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()

    # фон определяем по углам: у сгенерированного спрайта они почти всегда пустые
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    base = tuple(sum(c[i] for c in corners) // len(corners) for i in range(3))

    def is_bg(c):
        return (abs(c[0] - base[0]) <= tolerance and
                abs(c[1] - base[1]) <= tolerance and
                abs(c[2] - base[2]) <= tolerance)

    # заливка от краёв: двумерный массив visited вместо рекурсии
    visited = bytearray(w * h)
    stack = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + \
            [(0, y) for y in range(1, h - 1)] + [(w - 1, y) for y in range(1, h - 1)]
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        idx = y * w + x
        if visited[idx]:
            continue
        if not is_bg(px[x, y]):
            continue
        visited[idx] = 1
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    alpha = Image.new("L", (w, h), 255)
    ap = alpha.load()
    for y in range(h):
        row = y * w
        for x in range(w):
            if visited[row + x]:
                ap[x, y] = 0

    # бинаризация: полупрозрачных пикселей в базе нет, antialias по краю не нужен
    if not feather:
        alpha = alpha.point(lambda v: 255 if v > 127 else 0)

    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def crop_to_content(img, pad=0):
    """Обрезает прозрачные поля и ставит спрайт на общий низ.

    Возвращает RGBA, обрезанный по непрозрачному содержимому (+pad пикселей).
    Нужно, чтобы спрайт занимал всю клетку атласа, а не висел по центру
    с пустотой вокруг.
    """
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1 = min(img.width, x1 + pad)
    y1 = min(img.height, y1 + pad)
    return img.crop((x0, y0, x1, y1))


def to_cell(img, cell_w, cell_h):
    """Вписывает спрайт в клетку cell_w x cell_h, прижимая к низу по центру.

    NEAREST: спрайт пиксельный. Прижимаем к низу — все кадры анимации должны
    стоять на одной «земле», иначе персонаж в прыжке «взлетает» относительно
    остальных.
    """
    img = crop_to_content(img)
    w, h = img.size
    if w == 0 or h == 0:
        return Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))

    scale = min(cell_w / w, cell_h / h)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    small = img.resize((nw, nh), Image.NEAREST)

    cell = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
    cell.paste(small, ((cell_w - nw) // 2, cell_h - nh), small)
    return cell


# ===========================================================================
#  Запись кадров в базу
# ===========================================================================
def write_frames(db_path, character_id, class_frames, main_frame_id=None,
                 cell_size=None, replace=True):
    """Пишет кадры в frames.

    :param class_frames: {"ходьба": [PIL.Image, ...], ...} — уже готовые к записи
    :param cell_size: (w, h) клетки; None — писать как есть
    :param replace: True — заменить прежние кадры этого класса у персонажа
    :return: (сколько записано, список предупреждений)
    """
    conn = connect(db_path)
    warns = []
    written = 0
    try:
        cols = table_columns(conn, "frames")
        if "character_id" not in cols:
            raise RuntimeError(
                "в базе нет колонки character_id — это старая версия схемы. "
                "Откройте базу через новую версию программы (database.py), "
                "чтобы таблица frames обновилась")

        mid = main_frame_id or get_main_frame_id(conn, character_id)

        for class_name, images in class_frames.items():
            if replace:
                cur = conn.execute(
                    "DELETE FROM frames WHERE class_name = ? AND character_id = ?",
                    (class_name, character_id))
                if cur.rowcount:
                    warns.append(f"{class_name}: заменено {cur.rowcount} прежних кадров")

            for img in images:
                if cell_size:
                    img = to_cell(img, *cell_size)
                buf = BytesIO()
                img.convert("RGBA").save(buf, format="PNG")
                conn.execute(
                    "INSERT INTO frames (class_name, frame_data, main_frame_id, "
                    "character_id) VALUES (?, ?, ?, ?)",
                    (class_name, buf.getvalue(), mid, character_id))
                written += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return written, warns


# ===========================================================================
#  Сборка 2D-атласа
# ===========================================================================
def build_atlas(db_path, character_id, classes=None, cell_w=None, cell_h=None,
                padding=1, bg=(0, 0, 0, 0)):
    """Собирает атлас: строка = класс позы, столбцы = кадры этого класса.

    Раскладка та же, что у исходных атласов проекта, поэтому готовый файл
    можно сразу прогнать через штатный резчик (image_splitter + frame_detector).

    ВНИМАНИЕ: для frame_detector нужен ПРОЗРАЧНЫЙ фон (он ищет ряды по альфе).
    bg=(0,0,0,0) — по умолчанию прозрачный.

    :param classes: список классов; None — все классы персонажа
    :return: (PIL.Image, [(класс, число кадров), ...])
    """
    conn = connect(db_path)
    try:
        if classes is None:
            classes = list_pose_classes(db_path, character_id)

        # собираем кадры по классам
        groups = []
        for cls in classes:
            rows = conn.execute(
                "SELECT frame_data FROM frames WHERE class_name = ? "
                "AND character_id = ? ORDER BY id",
                (cls, character_id)).fetchall()
            imgs = []
            for (blob,) in rows:
                try:
                    imgs.append(Image.open(BytesIO(blob)).convert("RGBA"))
                except Exception:
                    continue
            if imgs:
                groups.append((cls, imgs))

        if not groups:
            raise RuntimeError("нет кадров для сборки атласа")

        if cell_w is None or cell_h is None:
            cw = max(i.width for _, imgs in groups for i in imgs)
            ch = max(i.height for _, imgs in groups for i in imgs)
            cell_w = cell_w or cw
            cell_h = cell_h or ch

        cols = max(len(imgs) for _, imgs in groups)
        step_x = cell_w + padding
        step_y = cell_h + padding
        W = padding + cols * step_x
        H = padding + len(groups) * step_y

        atlas = Image.new("RGBA", (W, H), bg)
        stat = []
        for r, (cls, imgs) in enumerate(groups):
            stat.append((cls, len(imgs)))
            for c, img in enumerate(imgs):
                cell = to_cell(img, cell_w, cell_h)
                atlas.paste(cell, (padding + c * step_x, padding + r * step_y), cell)
        return atlas, stat
    finally:
        conn.close()


def save_atlas(atlas, out_path):
    """Сохраняет атлас в PNG. Возвращает путь."""
    folder = os.path.dirname(os.path.abspath(out_path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    atlas.save(out_path, format="PNG")
    return out_path


# ===========================================================================
#  Запуск генерации в venv kohya
# ===========================================================================
def find_python(kohya_root):
    """python из venv kohya — там есть torch и diffusers."""
    for rel in (os.path.join("venv", "Scripts", "python.exe"),
                os.path.join("venv", "bin", "python"),
                os.path.join(".venv", "Scripts", "python.exe")):
        p = os.path.join(kohya_root, rel)
        if os.path.isfile(p):
            return p
    return None


def make_job(model, lora, lora_scale, kohya_root, out_dir, tasks, init=None,
             width=512, height=512, steps=24, cfg=7.0, negative=DEFAULT_NEGATIVE):
    """Собирает словарь задания для sd_generate.py."""
    return {
        "model": os.path.abspath(model),
        "lora": os.path.abspath(lora) if lora else "",
        "lora_scale": float(lora_scale),
        "kohya_root": os.path.abspath(kohya_root) if kohya_root else "",
        "out_dir": os.path.abspath(out_dir),
        "width": int(width), "height": int(height),
        "steps": int(steps), "cfg": float(cfg),
        "negative": negative,
        "init": os.path.abspath(init) if init else "",
        "tasks": tasks,
    }


def save_job(job, folder):
    """Пишет job.json рядом с результатами — по нему можно повторить прогон."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "job.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    return path


def run_generation(python_exe, script_path, job_path, on_line, should_stop=None,
                   offline=False, diffusers_config=""):
    """Запускает sd_generate.py и отдаёт строки лога в on_line.

    Читаем посимвольно и считаем концом строки и '\\n', и '\\r' — так же, как
    run_training в lora_train.py: diffusers пишет прогресс через '\\r'.

    :param offline: True — запретить сеть (только если конфиг SD уже в кэше HF
                    или передан своим путём в diffusers_config)
    :param diffusers_config: папка с конфигами diffusers для полностью офлайн-
                    запуска; передаётся воркеру через ISKRA_SD_CONFIG
    :return: код возврата; -1 — прервано пользователем, -2 — не запустилось.
    """
    cmd = [python_exe, script_path, "--job", job_path]
    return _run_worker(cmd, script_path, on_line, should_stop,
                       offline=offline, diffusers_config=diffusers_config)


def run_selftest(python_exe, script_path, on_line, kohya_root=""):
    """Самопроверка окружения в venv: torch, CUDA, diffusers, конфиги SD."""
    cmd = [python_exe, script_path, "--selftest"]
    return _run_worker(cmd, script_path, on_line, None, kohya_root=kohya_root)


# Воркер sd_generate.py печатает значимые строки только с этими тегами.
# Всё без тега — чужой шум (triton/xformers-предупреждения и их traceback,
# варнинги urllib и tqdm). Показываем его только если процесс упал: иначе
# реальная причина падения могла бы затеряться вместе с безобидным шумом.
_WORKER_TAGS = ("INFO ", "ERROR ", "FRAME ", "PROGRESS ", "SAVED ", "DONE ")


def _worker_meaningful(line):
    """True, если строка — служебное сообщение воркера, а не внешний шум."""
    return line.startswith(_WORKER_TAGS)


def _run_worker(cmd, script_path, on_line, should_stop, kohya_root="",
                offline=False, diffusers_config=""):
    """Общий запуск воркера: разбор stdout по '\\n' и '\\r'."""
    env = os.environ.copy()
    env["TF_CPP_MIN_LOG_LEVEL"] = "3"
    env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # СЕТЬ НЕ ЗАПРЕЩАЕМ. from_single_file берёт из .safetensors только веса,
    # а конфиги архитектуры (unet/vae/tokenizer) догружает из кэша HuggingFace.
    # HF_HUB_OFFLINE=1 ронял загрузку с LocalEntryNotFoundError. Скачивается
    # лишь маленький конфиг-репозиторий (json + словарь, десятки МБ), а не 2 ГБ
    # весов, и один раз — дальше всё берётся из кэша офлайн.
    if offline:
        env["HF_HUB_OFFLINE"] = "1"
    if kohya_root:
        env["ISKRA_KOHYA_ROOT"] = os.path.abspath(kohya_root)
    if diffusers_config:
        env["ISKRA_SD_CONFIG"] = os.path.abspath(diffusers_config)

    try:
        proc = subprocess.Popen(
            cmd, cwd=os.path.dirname(os.path.abspath(script_path)),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1, env=env)
    except FileNotFoundError as e:
        on_line(f"ERROR не запустилось: {e}")
        return -2

    buf = ""
    noise = []      # строки без тега: показываем только при падении
    try:
        while True:
            ch = proc.stdout.read(1)
            if not ch:
                break
            if ch in ("\r", "\n"):
                line = buf.strip()
                buf = ""
                if line:
                    if _worker_meaningful(line):
                        on_line(line)
                    elif len(noise) < 60:
                        noise.append(line)
                if should_stop and should_stop():
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    on_line("ERROR прервано пользователем")
                    return -1
            else:
                buf += ch
        if buf.strip() and _worker_meaningful(buf.strip()):
            on_line(buf.strip())
    finally:
        if proc.stdout:
            proc.stdout.close()
    rc = proc.wait()
    # процесс упал, а служебного ERROR не хватило — сливаем накопленный шум:
    # среди него настоящая причина (MemoryError, битый вес, нехватка модуля)
    if rc != 0 and noise:
        on_line("  ── вывод процесса перед падением ──")
        for line in noise[-15:]:
            on_line("    " + line[:200])
    return rc


def timestamp():
    return time.strftime("%Y%m%d_%H%M%S")