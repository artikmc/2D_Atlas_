# -*- coding: utf-8 -*-
"""
Экспорт датасета для обучения LoRA (Stable Diffusion / kohya_ss).

Берёт кадры из SQLite-базы (сгруппированные по персонажу и классу) и пишет
папку вида:

    dataset/
      prue3/                      # персонаж (латиницей, fs-safe)
        prue3_standing_0001.png   # кадр, апскейлнут NEAREST до 512x512 RGBA
        prue3_standing_0001.txt   # caption, одна строка тегов
        prue3_standing_0002.png
        ...

Решения, заложенные здесь (обсуждены с пользователем):
  * Формат caption — «гибрид»: триггер + общие теги персонажа + поза из класса.
    Индекс кадра в caption НЕ пишется (модель его не читает).
  * Прозрачный фон оставляем как есть, добавляем тег 'transparent background'.
  * Мелкий спрайт (напр. 22x45) НЕЛЬЗЯ отдавать SD как есть: сеть «смотрит» на
    512x512. Апскейлим NEAREST (без размытия пикселей) и вставляем по центру в
    квадрат 512x512 с прозрачными полями.
  * Имена папок/файлов — латиницей и fs-safe: kohya/torch на Windows падает на
    кириллице и на символах '\\ / : * ? "'.

Модуль не требует GPU и не импортирует torch — это чистый PIL + sqlite3.
"""

import os
import re
import sqlite3

from PIL import Image

# --- куда пишется датасет (относительно запускаемой папки проекта) ---
DEFAULT_DATASET_ROOT = "dataset"

# --- обязательные теги стиля: спрайт всегда пиксельный, всегда на прозрачке ---
STYLE_TAGS = ["pixel art", "sprite", "transparent background"]

# --- общие теги персонажа: id_персонажа -> список тегов.
#     Задаёт человек один раз; приклеивается ко всем caption этого персонажа.
#     Ключ — integer id из таблицы characters.
COMMON_TAGS = {
    16: ["1girl", "red demon", "horns"],  # «прое 3» — правьте под себя
    18: ["1boy", "brown hair", "beard", "brown clothes", "boots"],   # ← добавить, теги под свой рисунок
}

# --- перевод классов-поз на английский (модель понимает английские слова).
#     Реестр ключей не важен: нормализуем к нижнему регистру.
RU_TO_EN_POSE = {
    "стояние": "standing",
    "стояние": "standing",   # частая опечатка в классе
    "ходьба": "walking",
    "бег": "running",
    "прыжок": "jumping",
    "падение": "falling",
    "смерть": "death",
    "бросок": "throwing",
    "прыжок в верх": "jump_up",
    "прыжок вверх": "jump_up",
    "атака": "attack",
    "удар": "hit",
    "idle": "standing",
}

# класс, который НЕ является позой (служебный кадр-оригинал)
MAIN_FRAME_CLASS = "основной кадр"

# целевой размер холста для SD
TARGET_SIZE = 512

_FS_BAD = re.compile(r'[\\/:*?"<>|]')


def transliterate(text):
    """Кириллица -> латиница (для имён папок и триггера). Латиницу оставляет.

    Минимальный маппинг — под наши имена («прое 3» -> «prue 3»). Если персонаж
    назван нестандартно, имя можно просто задать латиницей в интерфейсе.
    """
    mapping = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    out = []
    for ch in text.lower():
        out.append(mapping.get(ch, ch))
    return "".join(out)


def safe_fs_name(name):
    """Убирает символы, запрещённые в именах файлов Windows."""
    name = _FS_BAD.sub("_", name)
    return name.strip().strip(".") or "untitled"


def make_trigger(name, character_id):
    """Уникальный триггер персонажа: транслит + id, всё склеено латиницей.

    id добавляем, чтобы два одинаково названных персонажа не столкнулись.
    """
    base = re.sub(r"[^a-z0-9]+", "", transliterate(name)) or f"char{character_id}"
    return f"{base}{character_id}"


def pose_word(class_name):
    """Русское название класса -> английское слово-поза (или сам класс латиницей)."""
    key = (class_name or "").strip().lower()
    if key in RU_TO_EN_POSE:
        return RU_TO_EN_POSE[key]
    # если класс уже латиницей («idle», «run») — оставляем как есть, пробелы->underscore
    ascii_name = transliterate(class_name).strip()
    return re.sub(r"\s+", "_", ascii_name) or "pose"


def build_caption(trigger, class_name, common_tags):
    """Одна строка тегов: триггер, общие теги, поза, теги стиля. Без повторов."""
    parts = [trigger]
    parts += list(common_tags)
    parts.append(pose_word(class_name))
    parts += STYLE_TAGS
    # дедупликация с сохранением порядка
    seen, out = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return ", ".join(out)


def upscale_pixel(img, scale_src=None):
    """Мелкий спрайт -> квадрат TARGET_SIZE x TARGET_SIZE RGBA.

    NEAREST-масштаб (пиксели остаются резкими), спрайт по центру, поля
    прозрачные. Если спрайт больше TARGET_SIZE — масштабируем целиком вниз,
    пропорции сохраняем.

    :param scale_src: кадр-эталон масштаба. Если задан, коэффициент считается
        по НЕМУ, а не по текущему кадру. Это важно: кадры в базе имеют разный
        размер (22x45, 28x45, 31x57 ...), и при подгонке каждого кадра отдельно
        один и тот же персонаж в датасете оказывался то крупнее, то мельче.
        С эталоном масштаб един на всего персонажа.
        Принимает PIL-изображение или кортеж (ширина, высота).
    """
    src = img.convert("RGBA")
    if scale_src is None:
        rw, rh = img.size
    elif isinstance(scale_src, (tuple, list)):
        rw, rh = scale_src[0], scale_src[1]
    else:
        rw, rh = scale_src.size
    w, h = src.size
    if w == 0 or h == 0:
        raise ValueError(f"пустой кадр {w}x{h}")
    if rw == 0 or rh == 0:
        raise ValueError(f"пустой эталон масштаба {rw}x{rh}")

    # коэффициент подгоняет ЭТАЛОН под холст, а применяется он ко всем кадрам
    scale = min(TARGET_SIZE / rw, TARGET_SIZE / rh)
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))

    # если кадр шире/выше эталона и не влез в холст — режем масштаб целиком,
    # иначе спрайт выйдет за границы
    fit = min(TARGET_SIZE / new_w, TARGET_SIZE / new_h)
    if fit < 1:
        new_w = max(1, int(new_w * fit))
        new_h = max(1, int(new_h * fit))

    big = src.resize((new_w, new_h), Image.NEAREST)
    canvas = Image.new("RGBA", (TARGET_SIZE, TARGET_SIZE), (0, 0, 0, 0))
    canvas.paste(big, ((TARGET_SIZE - new_w) // 2, (TARGET_SIZE - new_h) // 2), big)
    return canvas


# --- обход базы -------------------------------------------------------------

def _conn_or_none(db_path):
    if not os.path.exists(db_path):
        return None
    return sqlite3.connect(db_path)


def load_dataset_units(conn):
    """Собирает из базы список единиц экспорта.

    Возвращает [(trigger, character_id, character_name, class_name, [blob,...])]
    только для персонажей, у которых реально есть кадры (пустых пропускаем).
    """
    cur = conn.cursor()
    names = dict(cur.execute("SELECT id, name FROM characters").fetchall())

    # группировка: (character_id, class_name) -> [frame_data]
    groups = {}
    for chid, cls, blob in cur.execute(
        "SELECT character_id, class_name, frame_data FROM frames "
        "WHERE class_name != ?", (MAIN_FRAME_CLASS,)
    ).fetchall():
        if chid is None:
            continue  # кадры без персонажа в датасет не идут (старая база)
        groups.setdefault((chid, cls), []).append(blob)

    units = []
    for (chid, cls), blobs in groups.items():
        chname = names.get(chid) or f"char{chid}"
        trigger = make_trigger(chname, chid)
        units.append((trigger, chid, chname, cls, blobs))
    # стабильный порядок: по персонажу, затем по классу
    units.sort(key=lambda u: (u[1], u[3]))
    return units


def export_dataset(db_path, out_root=DEFAULT_DATASET_ROOT, dry_run=False):
    """Экспортирует кадры из БД в структуру датасета для kohya_ss.

    :param db_path: путь к atlas_database.db
    :param out_root: папка, куда писать dataset/
    :param dry_run: True — ничего не писать на диск, только собрать и вернуть
                    описание (для предпросмотра и тестов).
    :return: dict со статистикой: персонажей, классов, кадров, записанных файлов.
    """
    conn = _conn_or_none(db_path)
    if conn is None:
        raise FileNotFoundError(f"база не найдена: {db_path}")
    try:
        units = load_dataset_units(conn)

        plan_files = []          # [(путь, caption)] — для dry_run и отчёта
        total_frames = 0
        characters = set()
        classes = set()

        # эталон масштаба: самый крупный кадр каждого персонажа.
        # нужен, чтобы персонаж во всём датасете был одного размера (см. upscale_pixel)
        char_ref_size = {}
        for trigger, chid, chname, cls, blobs in units:
            for blob in blobs:
                from io import BytesIO as _B
                size = Image.open(_B(blob)).size
                area = size[0] * size[1]
                cur = char_ref_size.get(chid)
                if cur is None or area > cur[0]:
                    char_ref_size[chid] = (area, size)

        for trigger, chid, chname, cls, blobs in units:
            folder = os.path.join(out_root, safe_fs_name(trigger))
            pose = pose_word(cls)
            common = COMMON_TAGS.get(chid, [])
            characters.add(trigger)
            classes.add(pose)
            ref_size = char_ref_size.get(chid, (0, None))[1]

            for i, blob in enumerate(blobs, start=1):
                total_frames += 1
                caption = build_caption(trigger, cls, common)
                stem = f"{trigger}_{pose}_{i:04d}"
                png_path = os.path.join(folder, stem + ".png")
                txt_path = os.path.join(folder, stem + ".txt")
                plan_files.append((png_path, txt_path, caption))

                if not dry_run:
                    from io import BytesIO
                    img = Image.open(BytesIO(blob))
                    # масштаб считаем от эталона персонажа, а не от текущего кадра
                    img = upscale_pixel(img, scale_src=ref_size)
                    os.makedirs(folder, exist_ok=True)
                    img.save(png_path, format="PNG")
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(caption)

        return {
            "characters": sorted(characters),
            "poses": sorted(classes),
            "frames": total_frames,
            "files": plan_files,
            "written": (not dry_run),
        }
    finally:
        conn.close()


def _report(info, db_path, out_root, dry):
    """Печатает человеческий отчёт: куда записано, сколько файлов, всё ли ровно."""
    print(f"База: {os.path.abspath(db_path)}")
    print(f"Персонажи: {info['characters']}")
    print(f"Позы: {info['poses']}")
    print(f"Кадров: {info['frames']}")

    if dry:
        print("\nРЕЖИМ ПРЕДПРОСМОТРА: диск не тронут, файлы не записаны.")
        print("\n--- caption ---")
        for png_path, txt_path, caption in info["files"][:8]:
            print(f"{png_path}\n    -> {caption}")
        return

    root = os.path.abspath(out_root)
    print(f"\nКуда записано: {root}")

    pngs = [p for p, _, _ in info["files"]]
    txts = [t for _, t, _ in info["files"]]
    print(f"Файлов: {len(pngs) + len(txts)}  (png: {len(pngs)}, txt: {len(txts)})")

    missing = [t for p, t, _ in info["files"] if not os.path.exists(t)]
    if missing:
        print(f"ВНИМАНИЕ: не записалось {len(missing)} txt, например {missing[0]}")

    # проверка единого масштаба: высота спрайта внутри холста должна совпадать
    from io import BytesIO as _B
    heights = set()
    for p in pngs:
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGBA")
        bb = im.getchannel("A").getbbox()
        if bb:
            heights.add(bb[3] - bb[1])
    if len(heights) == 1:
        print(f"Масштаб: единый (высота спрайта {heights.pop()} px во всех кадрах)")
    else:
        print(f"ВНИМАНИЕ: разный масштаб, высоты спрайтов {sorted(heights)}")
        print("  -> значит работает СТАРАЯ версия файла (без эталона масштаба)")

    # персонажи без тегов внешности
    no_tags = [c for c in info["characters"]]
    if no_tags:
        print(f"\nПапки персонажей: {', '.join(no_tags)}")
        print("Если в caption нет описания внешности — впишите теги в COMMON_TAGS.")


def verify_dataset(db_path, out_root=DEFAULT_DATASET_ROOT):
    """Проверяет уже записанный датасет: пары png/txt, единый коэффициент, captions.

    Возвращает (ok, [сообщения]).
    """
    msgs = []
    ok = True
    if not os.path.isdir(out_root):
        return False, [f"папки нет: {os.path.abspath(out_root)} — сначала запустите экспорт"]

    conn = _conn_or_none(db_path)
    if conn is None:
        return False, [f"база не найдена: {db_path}"]
    try:
        # исходные размеры по классам — из базы
        cur = conn.cursor()
        # для каждой позы — ВИДИМАЯ высота спрайта в исходнике (по альфа-каналу).
        # именно она масштабируется; высота всего кадра включает прозрачные поля
        # и у разных кадров разная, поэтому сравнивать надо bbox
        src_bbox_h = {}
        for cls, blob in cur.execute(
            "SELECT class_name, frame_data FROM frames WHERE class_name != ?",
            (MAIN_FRAME_CLASS,)
        ).fetchall():
            from io import BytesIO as _B
            im = Image.open(_B(blob)).convert("RGBA")
            bb = im.getchannel("A").getbbox()
            if bb:
                src_bbox_h.setdefault(pose_word(cls), set()).add(bb[3] - bb[1])
    finally:
        conn.close()

    checked = 0
    ratios = {}
    for folder in sorted(os.listdir(out_root)):
        fdir = os.path.join(out_root, folder)
        if not os.path.isdir(fdir):
            continue
        files = os.listdir(fdir)
        pngs = sorted(f for f in files if f.endswith(".png"))
        txts = set(f for f in files if f.endswith(".txt"))

        if not pngs:
            msgs.append(f"{folder}: нет png")
            ok = False
            continue

        for p in pngs:
            base = p[:-4]
            tpath = os.path.join(fdir, base + ".txt")
            if base + ".txt" not in txts:
                msgs.append(f"{folder}/{p}: нет парного .txt")
                ok = False
                continue
            caption = open(tpath, encoding="utf-8").read().strip()
            if not caption:
                msgs.append(f"{folder}/{p}: пустой caption")
                ok = False

            # коэффициент = высота спрайта на холсте / высота исходника
            pose = base.split("_")[1] if "_" in base else None
            if pose and pose in src_bbox_h:
                im = Image.open(os.path.join(fdir, p)).convert("RGBA")
                bb = im.getchannel("A").getbbox()
                if bb:
                    out_h = bb[3] - bb[1]
                    # исходник для этого кадра: берём ближайшую по высоте видимую
                    # высоту из базы (в одной позе кадры одной высоты)
                    cand = src_bbox_h[pose]
                    src_h = min(cand, key=lambda v: abs(out_h / v - 10.45)) \
                        if len(cand) > 1 else next(iter(cand))
                    ratios.setdefault(pose, set()).add(round(out_h / src_h, 2))
            checked += 1

    if ratios:
        allr = set()
        for v in ratios.values():
            allr |= v
        # допускаем разброс в сотых: округление пикселей
        if max(allr) - min(allr) <= 0.03:
            msgs.append(f"масштаб: единый коэффициент ~{sorted(allr)[0]} "
                        f"во всех позах ({', '.join(sorted(ratios))})")
        else:
            msgs.append(f"ВНИМАНИЕ: коэффициент съезжает: {ratios}")
            ok = False

    msgs.append(f"проверено кадров: {checked}")
    return ok, msgs


if __name__ == "__main__":
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else "atlas_database.db"
    dry = "--dry" in sys.argv
    check = "--check" in sys.argv

    if check:
        ok, msgs = verify_dataset(db)
        for m in msgs:
            print(" ", m)
        print("\nИТОГ:", "всё в порядке" if ok else "есть проблемы (см. выше)")
        raise SystemExit(0 if ok else 1)

    try:
        info = export_dataset(db, dry_run=dry)
    except FileNotFoundError as e:
        print(f"ОШИБКА: {e}")
        print("Запускайте из папки проекта, где лежит atlas_database.db,")
        print('или укажите путь: python dataset_export.py "G:\\путь\\к\\базе.db"')
        raise SystemExit(1)

    print(f"База: {os.path.abspath(db)}")
    print(f"Персонажи: {info['characters']}")
    print(f"Позы: {info['poses']}")
    print(f"Кадров: {info['frames']}")

    if dry:
        print("\nРЕЖИМ ПРЕДПРОСМОТРА: диск не тронут, файлы не записаны.")
        print("\n--- caption ---")
        for png_path, txt_path, caption in info["files"][:6]:
            print(f"{os.path.basename(png_path)}\n    -> {caption}")
        raise SystemExit(0)

    print(f"\nКуда записано: {os.path.abspath(DEFAULT_DATASET_ROOT)}\\{', '.join(info['characters'])}")
    print(f"Файлов: {len(info['files']) * 2}  (png + txt на каждый кадр)")
    print()

    ok, msgs = verify_dataset(db)
    for m in msgs:
        print(" ", m)
    print("\nИТОГ:", "датасет готов" if ok else "есть проблемы (см. выше)")
    raise SystemExit(0 if ok else 1)


