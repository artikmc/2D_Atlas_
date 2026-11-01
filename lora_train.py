# -*- coding: utf-8 -*-
"""Подготовка обучения LoRA для kohya_ss: пресеты, конфиг TOML, проверка готовности.

Здесь нет GUI — только расчёты и работа с файлами. Так же устроен
dataset_export.py: логика отдельно, окно отдельно (export_window.py).

Почему отдельный файл: обучение можно будет запускать и из консоли,
без интерфейса, и тестировать без открывания окна.
"""

import os
import shutil
import subprocess

# ---------------------------------------------------------------------------
# Пресет под RTX 3050 8 ГБ, SD 1.5, кадры 512x512.
# Значения подобраны так, чтобы 8 ГБ VRAM хватило без вылета по памяти.
# Меняются в окне, здесь — только значения по умолчанию.
# ---------------------------------------------------------------------------
PRESET_3050 = {
    "название": "RTX 3050 8 ГБ / SD 1.5",
    "resolution": "512,512",
    "network_dim": 16,          # размер LoRA: больше — точнее, но риск переобучения
    "network_alpha": 8,         # обычно половина от dim
    "learning_rate": 1e-4,
    "text_encoder_lr": 5e-5,    # текстовый энкодер учим мягче
    "unet_lr": 1e-4,
    "train_batch_size": 1,      # 8 ГБ не потянут больше при 512
    "max_train_epochs": 25,
    "save_every_n_epochs": 5,
    "optimizer_type": "AdamW8bit",   # экономит память
    "lr_scheduler": "cosine",
    "mixed_precision": "fp16",
    "gradient_checkpointing": True,  # главный способ влезть в 8 ГБ
    "cache_latents": True,           # быстрее: латенты считаются один раз
    "keep_tokens": 1,                # триггер персонажа не перемешивается
    "shuffle_caption": True,
    "seed": 42,
}


def to_toml(values):
    """Собирает текст TOML из словаря.

    Пишем сами, а не библиотекой: нужны только строки, числа и true/false,
    а лишняя зависимость в проекте ни к чему.
    """
    lines = []
    for key, val in values.items():
        if isinstance(val, bool):
            lines.append(f"{key} = {'true' if val else 'false'}")
        elif isinstance(val, (int, float)):
            lines.append(f"{key} = {val}")
        else:
            # пути в Windows содержат обратные слэши — в TOML их надо удвоить
            safe = str(val).replace("\\", "\\\\")
            lines.append(f'{key} = "{safe}"')
    return "\n".join(lines) + "\n"


def prepare_train_dir(dataset_root, repeats=1):
    """Готовит папку в той структуре, которую ждёт kohya.

    kohya берёт train_data_dir как родительскую папку, а внутри читает
    подпапки вида '10_man18': число перед подчёркиванием — сколько раз
    повторить кадры за эпоху, после — имя концепта (оно попадает в caption).

    У нас датасет лежит как dataset/man18/*.png. Копируем в
    dataset/train/10_man18/, чтобы структура была ровно та, что нужно.

    :return: (путь_к_train_data_dir, сколько_файлов_скопировано, список_сообщений)
    """
    msgs = []
    if not os.path.isdir(dataset_root):
        return None, 0, [f"нет папки датасета: {os.path.abspath(dataset_root)}"]

    chars = [d for d in sorted(os.listdir(dataset_root))
             if os.path.isdir(os.path.join(dataset_root, d)) and d != "train"]
    if not chars:
        return None, 0, [f"в {dataset_root} нет папок персонажей"]

    train_root = os.path.join(dataset_root, "train")
    os.makedirs(train_root, exist_ok=True)

    total = 0
    for ch in chars:
        src = os.path.join(dataset_root, ch)
        dst = os.path.join(train_root, f"{repeats}_{ch}")
        os.makedirs(dst, exist_ok=True)
        n = 0
        for f in sorted(os.listdir(src)):
            if not f.lower().endswith((".png", ".txt")):
                continue
            shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
            n += 1
        total += n
        msgs.append(f"{ch}: {n} файлов -> {repeats}_{ch}")

    return train_root, total, msgs


def find_kohya(root):
    """Ищет внутри папки kohya_ss скрипт обучения и python из его venv.

    Разные версии kohya кладут train_network.py по-разному: в корень
    или в подпапку sd-scripts. Проверяем оба места.

    :return: dict с ключами python, script, ok и msg
    """
    res = {"ok": False, "python": None, "script": None, "msg": ""}
    if not root or not os.path.isdir(root):
        res["msg"] = "папка kohya не указана или её нет"
        return res

    candidates = [
        os.path.join(root, "sd-scripts", "train_network.py"),
        os.path.join(root, "train_network.py"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            res["script"] = c
            break
    if res["script"] is None:
        res["msg"] = "не найден train_network.py (проверены корень и sd-scripts)"
        return res

    pythons = [
        os.path.join(root, "venv", "Scripts", "python.exe"),
        os.path.join(root, "venv", "bin", "python"),
        os.path.join(root, ".venv", "Scripts", "python.exe"),
    ]
    for p in pythons:
        if os.path.isfile(p):
            res["python"] = p
            break
    if res["python"] is None:
        # venv не найден — попробуем системный python, но это предупреждение
        res["python"] = "python"
        res["msg"] = "venv не найден, будет использован системный python"
        res["ok"] = True
        return res

    res["ok"] = True
    res["msg"] = "kohya найдена"
    return res


def cuda_check(python_exe, timeout=60):
    """Спрашивает у python из kohya, видит ли он CUDA.

    Это единственный честный способ узнать, что обучение пойдёт на
    видеокарте, а не на процессоре. Занимает несколько секунд: torch
    грузится долго, поэтому и таймаут большой.
    """
    try:
        out = subprocess.run(
            [python_exe, "-c",
             "import torch;print(torch.__version__);"
             "print('cuda', torch.cuda.is_available());"
             "print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')"],
            capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, "python не найден: " + str(python_exe)
    except subprocess.TimeoutExpired:
        return False, f"torch не ответил за {timeout} секунд"

    if out.returncode != 0:
        return False, "torch не установлен в этом python:\n" + (out.stderr or "")[-300:]

    lines = [l.strip() for l in out.stdout.strip().splitlines() if l.strip()]
    ok = len(lines) >= 2 and lines[1].endswith("True")
    return ok, " / ".join(lines[:3])


def build_config(train_data_dir, output_dir, base_model, output_name, params):
    """Собирает словарь параметров конфига kohya из пресета и путей."""
    cfg = {
        "pretrained_model_name_or_path": base_model,
        "train_data_dir": train_data_dir,
        "output_dir": output_dir,
        "output_name": output_name,
        "network_module": "networks.lora",
        "save_model_as": "safetensors",
        "save_precision": "fp16",
        "caption_extension": ".txt",
        "enable_bucket": True,          # разные соотношения сторон — ок
        "min_bucket_reso": 256,
        "max_bucket_reso": 768,
        "clip_skip": 1,
        "lr_warmup_steps": 0,
        "no_half_vae": False,
    }
    cfg.update(params)
    return cfg


def train_command(python_exe, script, config_path):
    """Готовая команда запуска. Возвращаем списком, без оболочки."""
    return [python_exe, script, "--config_file", config_path]


def check_ready(dataset_root, base_model, kohya_root, output_dir, run_cuda=False):
    """Проверяет всё, что нужно для обучения, и возвращает список строк.

    Каждая строка уже готова к печати в лог. 'ОК' — всё хорошо,
    'НЕТ' — без этого обучение не пойдёт, 'ВНИМАНИЕ' — пойдёт, но с оговоркой.
    """
    out = []

    # 1. датасет
    chars = []
    if os.path.isdir(dataset_root):
        chars = [d for d in sorted(os.listdir(dataset_root))
                 if os.path.isdir(os.path.join(dataset_root, d)) and d != "train"]
    if not chars:
        out.append(f"НЕТ: папка датасета пуста или не найдена: {os.path.abspath(dataset_root)}")
    else:
        frames = 0
        missing_txt = 0
        for ch in chars:
            for f in os.listdir(os.path.join(dataset_root, ch)):
                if f.lower().endswith(".png"):
                    frames += 1
                    t = os.path.join(dataset_root, ch, f[:-4] + ".txt")
                    if not os.path.isfile(t):
                        missing_txt += 1
        out.append(f"ОК: датасет — {len(chars)} персонаж(ей), {frames} кадров")
        if missing_txt:
            out.append(f"ВНИМАНИЕ: у {missing_txt} кадров нет .txt — они будут без подписи")
        if frames < 15:
            out.append(f"ВНИМАНИЕ: кадров мало ({frames}); для LoRA обычно нужно от 15")

    # 2. базовая модель
    if not base_model or not os.path.isfile(base_model):
        out.append("НЕТ: не найдена базовая модель (.safetensors SD 1.5)")
    else:
        size_gb = os.path.getsize(base_model) / (1024 ** 3)
        out.append(f"ОК: базовая модель {os.path.basename(base_model)} ({size_gb:.2f} ГБ)")
        if size_gb < 1.5:
            out.append("ВНИМАНИЕ: файл меньше 1.5 ГБ — похоже, это не полная модель SD 1.5")

    # 3. kohya
    k = find_kohya(kohya_root)
    if k["ok"]:
        out.append(f"ОК: {k['script']}")
        out.append(f"ОК: python — {k['python']}")
        if k["msg"] and k["msg"] != "kohya найдена":
            out.append("ВНИМАНИЕ: " + k["msg"])
    else:
        out.append("НЕТ: " + k["msg"])

    # 4. папка для результата
    try:
        os.makedirs(output_dir, exist_ok=True)
        out.append(f"ОК: результаты пойдут в {os.path.abspath(output_dir)}")
    except OSError as e:
        out.append(f"НЕТ: папку результата создать нельзя: {e}")

    # 5. CUDA — только по явному запросу, потому что это долго
    if run_cuda and k["ok"]:
        ok, info = cuda_check(k["python"])
        out.append(("ОК: CUDA — " if ok else "НЕТ: CUDA — ") + info)

    return out


def total_steps(frames, repeats, epochs, batch_size=1):
    """Сколько всего шагов обучения получится.

    Шаги = кадры × повторы × эпохи / размер батча.
    Для символа LoRA нормально 500–1500 шагов. Меньше — недотренируется,
    больше — персонаж начнёт повторять картинки из датасета.
    """
    if batch_size <= 0:
        return 0
    return int(frames * repeats * epochs / batch_size)


def write_config(cfg, path):
    """Записывает конфиг TOML на диск, возвращает путь."""
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(to_toml(cfg))
    return path


def run_training(cmd, cwd, on_line, should_stop=None):
    """Запускает обучение и отдаёт каждую строку лога в on_line.

    Вывод kohya идёт построчно, поэтому строка появляется в окне сразу,
    а не после окончания обучения (оно идёт десятки минут).

    :param cmd: список аргументов (без shell)
    :param cwd: рабочая папка — kohya требует запуска из своей папки
    :param on_line: функция(str) для каждой строки
    :param should_stop: функция() -> bool; True прерывает обучение
    :return: код возврата (0 — успешно, -1 — прервано)
    """
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1)
    except FileNotFoundError as e:
        on_line(f"НЕ ЗАПУСТИЛОСЬ: {e}")
        return -2

    try:
        for line in proc.stdout:
            on_line(line.rstrip())
            if should_stop and should_stop():
                proc.terminate()
                on_line("ОБУЧЕНИЕ ПРЕРВАНО пользователем")
                return -1
    finally:
        if proc.stdout:
            proc.stdout.close()
    return proc.wait()


if __name__ == "__main__":
    import sys
    print(__doc__)
    print("Пресет:", PRESET_3050["название"])
    print("Проверка примером (пути-заглушки):")
    for line in check_ready("dataset", "model.safetensors", "kohya_ss", "output"):
        print(" ", line)