# -*- coding: utf-8 -*-
"""Генерация кадров спрайта через diffusers. Запускается python ИЗ venv kohya_ss.

Этот файл НИКОГДА не импортируется программой: torch и diffusers стоят только
в виртуальном окружении kohya, а GUI работает на системном Python. Поэтому
ai_generate.py вызывает этот скрипт отдельным процессом и читает его stdout.

Почему один запуск на все кадры: загрузка 2 ГБ весов и LoRA занимает десятки
секунд. Если вызывать скрипт на каждый класс (стояние, бег, ...), одно и то же
грузолось бы пять раз. Поэтому скрипт получает JSON-задание со списком задач и
грузит пайплайн ровно один раз.

Формат задания (job.json), его пишет ai_generate.py:

    {
      "model": "G:/models/dreamshaper_8.safetensors",
      "lora": "G:/.../man18_lora.safetensors",
      "lora_scale": 1.0,
      "kohya_root": "G:/kohya_ss",
      "out_dir": "G:/.../ai_frames/20261102_204000",
      "width": 512, "height": 512,
      "steps": 24, "cfg": 7.0,
      "negative": "blurry, photo, 3d render",
      "init": "G:/.../reference.png",
      "tasks": [
        {"prefix": "running", "prompt": "man18, running, ...", "count": 4,
         "seed": 42, "strength": 0.5, "strength_end": 0.75}
      ]
    }

Строки, которые читает окно через ai_generate.run_generation:
    INFO <текст>         — что происходит
    FRAME <i>/<n> ...    — начали кадр
    PROGRESS <i>/<n> шаг <s>/<steps>
    SAVED <путь>         — кадр сохранён
    DONE <сколько>
    ERROR <текст>        — и дальше traceback в stdout

Про фон: kohya при обучении видела прозрачность как ЧЁРНЫЙ (RGB под альфой =
0,0,0 — проверено на export_final/man18/*.png). Поэтому модель рисует спрайт на
чёрном. Вырезание фона делает ai_generate.py на системном Python, где есть PIL.
"""

import argparse
import json
import os
import sys
import traceback


def log(kind, msg):
    print(f"{kind} {msg}".rstrip(), flush=True)


def find_original_config(kohya_root):
    """"YAML-конфиг SD 1.5 из kohya — attention-конфиг для from_single_file.

    ВАЖНО: этот yaml решает ТОЛЬКО блоки attention. Конфиг архитектуры
    (model_index.json, unet/vae) и словарь токенизатора diffusers берёт
    ОТДЕЛЬНО из кэша HuggingFace — см. find_sd_config_cache. Одного yaml для
    офлайна недостаточно; именно на этом и падал первый запуск.
    """
    if not kohya_root:
        return None
    names = ("v1-inference.yaml", "v2-inference-v.yaml")
    # известные раскладки kohya + запасной обход: файл кочует между версиями
    for cand in [os.path.join(kohya_root, "sd-scripts", "configs", n) for n in names] + \
                [os.path.join(kohya_root, "configs", n) for n in names] + \
                [os.path.join(kohya_root, "configs", "stable-diffusion", n) for n in names]:
        if os.path.isfile(cand):
            return cand
    try:
        for root, dirs, files in os.walk(kohya_root):
            dirs[:] = [d for d in dirs if d not in ("venv", ".venv", ".git")]
            for name in names:
                if name in files:
                    return os.path.join(root, name)
    except OSError:
        pass
    return None


def hf_cache_roots():
    """Возможные папки кэша HuggingFace (HF_HOME, ~/.cache, Windows AppData)."""
    roots = []
    if os.environ.get("HF_HOME"):
        roots += [os.path.join(os.environ["HF_HOME"], "hub"), os.environ["HF_HOME"]]
    roots.append(os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"))
    appdata = os.environ.get("LOCALAPPDATA")
    if appdata:
        roots.append(os.path.join(appdata, "huggingface", "hub"))
    return [r for r in roots if r]


def _find_snapshot(repo_slug, need_file):
    """Снимок репозитория в кэше HF, где есть файл need_file."""
    for root in hf_cache_roots():
        snaps = os.path.join(root, "models--" + repo_slug, "snapshots")
        if not os.path.isdir(snaps):
            continue
        for snap in sorted(os.listdir(snaps), reverse=True):
            p = os.path.join(snaps, snap)
            if os.path.isfile(os.path.join(p, need_file)):
                return p
    return None


def find_sd_config_cache(repo="stable-diffusion-v1-5--stable-diffusion-v1-5"):
    """Есть ли в кэше HF конфиги SD 1.5 (model_index.json), которые тянет
    from_single_file. Без них при первом запуске идёт скачивание с HF."""
    return _find_snapshot(repo, "model_index.json")


def find_clip_tokenizer():
    """Токенизатор CLIP в кэше HF — отдельный от конфига архитектуры."""
    return _find_snapshot("openai--clip-vit-large-patch14", "tokenizer_config.json")


def selftest():
    """Самопроверка окружения без загрузки модели.

    Печатает то, что важно знать до генерации: есть ли torch/diffusers, видна
    ли видеокарта, найдётся ли конфиг и токенизатор оффлайн.
    """
    rc = 0
    has_cuda = True
    try:
        import torch
        log("INFO", f"torch {torch.__version__}")
        if torch.cuda.is_available():
            log("INFO", f"CUDA: да, {torch.cuda.get_device_name(0)}")
            try:
                free, total = torch.cuda.mem_get_info()
                log("INFO", f"видеопамять: {total / 1024 ** 3:.1f} ГБ, "
                            f"свободно {free / 1024 ** 3:.1f} ГБ")
            except Exception:
                pass
        else:
            # не ошибка запуска, но и не «всё хорошо»: пишем прямо, что это значит
            log("INFO", "CUDA: НЕТ — генерация пойдёт на процессоре, это очень медленно")
            has_cuda = False
    except Exception as e:
        log("ERROR", f"torch не импортируется: {e}")
        return 2

    try:
        import diffusers
        log("INFO", f"diffusers {diffusers.__version__}")
    except Exception as e:
        log("ERROR", f"diffusers не импортируется:  {e}")
        return 2

    cfg = find_original_config(os.environ.get("ISKRA_KOHYA_ROOT", ""))
    log("INFO", f"yaml attention-конфиг: {cfg or 'не найден (diffusers сам подставит SD 1.5)'}")

    # вот что реально блокировало первый запуск: конфиги архитектуры SD
    cached = find_sd_config_cache()
    tok = find_clip_tokenizer()
    if cached:
        log("INFO", "конфиги SD 1.5 в кэше HF: ЕСТЬ — интернет для запуска не нужен")
    else:
        log("INFO", "конфиги SD 1.5 в кэше HF: НЕТ — первый запуск скачает их с "
                    "HuggingFace, нужен интернет.")
        log("INFO", "Скачивается только конфиг (несколько МБ), не 2 ГБ весов; "
                    "дальше всё берётся из кэша офлайн.")
    log("INFO", "токенизатор CLIP: " +
        ("есть в кэше" if tok else "нет — скачается при первом запуске"))

    # peft нужен только для современного пути; без него работает ручное наложение    
    try:
        import peft  # noqa: F401
        log("INFO", "peft: есть — LoRA подключится штатно")
    except Exception:
        log("INFO", "peft: нет — LoRA подключится вручную (это нормально)")

    if not has_cuda:
        log("INFO", "ИТОГ: движок рабочий, но без CUDA генерация будет очень медленной")
    return rc


def _load_lora_state(path):
    """Читает .safetensors веса. Отдельная функция — её подменяют в тестах."""
    from safetensors.torch import load_file
    return load_file(path)


_TEST_LORA_STUB = None


def apply_lora_manually(module, lora_path, scale=1.0, prefix="lora_unet_",
                        state=None):
    """Накладывает LoRA на модуль без peft — руками, по определению.

    Зачем: в venv kohya пакет peft не установлен, а load_lora_weights в
    diffusers 0.32 требует его безусловно ("PEFT backend is required").
    Формат kohya плоский и документированный:

        lora_unet_<модуль>.lora_down.weight   (r, in)
        lora_unet_<модуль>.lora_up.weight     (out, r)
        lora_unet_<модуль>.alpha              (скаляр; иначе alpha = r)

    Эффект тот же, что у peft: W += scale * alpha/r * (up @ down).

    :param module: UNet или text_encoder из пайплайна
    :param lora_path: путь к .safetensors от kohya
    :param scale: сила LoRA
    :param prefix: "lora_unet_" для UNet, "lora_te_" для текстового энкодера
    :param state: уже прочитанные веса (чтобы не читать файл дважды)
    :return: число наложенных слоёв; 0 — формат не распознан
    """
    import torch

    sd = state if state is not None else _load_lora_state(lora_path)
    keys = list(sd.keys())

    # префикс не угадываем: у kohya это lora_unet_/lora_te_, но бывают
    # выгрузки без префикса. Берём тот, под которым реально есть lora_down.
    if not any(k.startswith(prefix) for k in keys):
        prefix = ""
        if not any(".lora_down.weight" in k for k in keys):
            return 0

    # имена модулей diffusers пишутся через точки (down_blocks.0.attentions),
    # kohya кодирует их подчёркиваниями, поэтому сверяем нормализованные имена
    mods = {}
    for name, m in module.named_modules():
        if hasattr(m, "weight"):
            mods[name.replace(".", "_")] = m

    # у ключа два «хвоста»: <модуль>.lora_down.weight | .lora_up.weight | .alpha
    suffixes = (".lora_down.weight", ".lora_up.weight", ".alpha")
    groups = {}
    for key in keys:
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        for suf in suffixes:
            if rest.endswith(suf):
                groups.setdefault(rest[:-len(suf)], {})[suf.lstrip(".")] = sd[key]
                break

    applied = 0
    skipped = 0          # слоёв, где что-то не совпало — считаем, но не роняем
    first_err = None     # покажем причину ровно один раз, а не 72 раза

    for base, part in groups.items():
        target = mods.get(base)
        if target is None:
            skipped += 1
            continue
        down = part.get("lora_down.weight")
        up = part.get("lora_up.weight")
        if down is None or up is None:
            skipped += 1
            continue
        try:
            # Kohya пишет два формата:
            #   линейный LoRA:  down (r,in)      up (out,r)
            #   conv-LoRA/LoCon: down (r,in,kh,kw) up (out,r,1,1)
            # torch.mm принимает только 2D, поэтому сворачиваем хвост размерностей
            # в плоскость (как это делает и сам peft), а потом возвращаем форму.
            dshape, ushape = tuple(down.shape), tuple(up.shape)
            r = dshape[0]
            if len(dshape) > 2:                 # conv-LoRA
                down2 = down.reshape(r, -1)     # (r, in*kh*kw)
                up2 = up.reshape(ushape[0], r)  # (out, r)
            else:
                down2, up2 = down, up
            alpha = part.get("alpha")
            alpha_v = float(alpha.reshape(-1)[0]) if alpha is not None else float(r)
            k = scale * alpha_v / float(r)
            delta = torch.mm(up2.float(), down2.float()) * k   # (out, in*kh*kw)
            w = target.weight
            want = tuple(w.shape)
            if tuple(delta.shape) != want:
                # conv-слой: delta плоская, вес 4D — приводим форму
                if len(want) >= 2 and delta.numel() == _numel(want):
                    delta = delta.reshape(*want)
                else:
                    skipped += 1
                    continue
            # складываем в float32 и только потом возвращаем dtype веса: на fp16
            # прямое сложение теряет младшие разряды, и за 24 шага это заметно
            w.data = (w.data.float() + delta).to(dtype=w.dtype, device=w.device)
            applied += 1
        except Exception as e:
            skipped += 1
            if first_err is None:
                first_err = f"{type(e).__name__}: {e}"
    return applied, skipped, first_err


def _numel(shape):
    n = 1
    for x in shape:
        n *= int(x)
    return n


def apply_lora_all(pipe, lora_path, scale=1.0):
    """Накладывает LoRA на UNet и на текстовый энкодер.

    Текстовая часть важна не меньше: именно она отвечает за то, насколько
    триггер-слово «узнаёт» персонажа. Без неё кадры похожи на референс, но
    персонаж «плывёт». Файл читается один раз на оба модуля.

    :return: (слоёв_unet, слоёв_te, пропущено_всего, первая_ошибка)
    """
    state = _load_lora_state(lora_path)
    n_unet, sk_unet, err1 = apply_lora_manually(pipe.unet, lora_path, scale,
                                                prefix="lora_unet_", state=state)
    n_te = sk_te = 0
    err2 = None
    text_encoder = getattr(pipe, "text_encoder", None)
    if text_encoder is not None:
        try:
            n_te, sk_te, err2 = apply_lora_manually(
                text_encoder, lora_path, scale, prefix="lora_te_", state=state)
        except Exception as e:
            err2 = f"{type(e).__name__}: {e}"
            log("INFO", f"текстовый энкодер пропущен: {err2}")
    return n_unet, n_te, sk_unet + sk_te, (err1 or err2)


def build_pipeline(job, torch):
    """Собирает пайплайн один раз. Возвращает (pipe, mode)."""
    from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline

    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    kwargs = {"torch_dtype": dtype, "safety_checker": None,
              "requires_safety_checker": False}

    cfg = find_original_config(job.get("kohya_root"))
    if cfg:
        kwargs["original_config_file"] = cfg
        log("INFO", f"original_config: {cfg}")
    else:
        log("INFO", "original_config не найден — diffusers может обратиться к HF")

    model = job["model"]
    log("INFO", f"загрузка модели: {model}")
    if job.get("init"):
        pipe = StableDiffusionImg2ImgPipeline.from_single_file(model, **kwargs)
        mode = "img2img"
    else:
        pipe = StableDiffusionPipeline.from_single_file(model, **kwargs)
        mode = "txt2img"

    try:
        pipe.enable_attention_slicing()   # 8 ГБ: без этого 512x512+LoRA может не влезть
    except Exception:
        pass

    lora = job.get("lora") or ""
    if lora:
        log("INFO", f"LoRA: {lora}")
        scale = float(job.get("lora_scale", 1.0))
        done = False
        # 1) современный путь: peft внутри diffusers
        try:
            pipe.load_lora_weights(
                os.path.dirname(os.path.abspath(lora)) or ".",
                weight_name=os.path.basename(lora),
                adapter_name="char",
            )
            try:
                pipe.set_adapters(["char"], adapter_weights=[scale])
            except Exception:
                pass
            log("INFO", "LoRA подключена (load_lora_weights)")
            done = True
        except Exception as e:
            log("INFO", f"load_lora_weights недоступен: {type(e).__name__}: {e}")

        # 2) без peft — накладываем веса на UNet вручную (формат kohya)
        if not done:
            try:
                n_unet, n_te, n_skip, err = apply_lora_all(pipe, lora, scale)
            except Exception as e:
                n_unet = n_te = n_skip = 0
                err = f"{type(e).__name__}: {e}"
                log("ERROR", f"ручное наложение LoRA упало полностью: {err}")
            if n_unet:
                msg = (f"LoRA подключена вручную (peft не нужен): "
                       f"UNet {n_unet} слоёв, текст {n_te}, сила {scale}")
                if n_skip:
                    msg += f" | пропущено {n_skip} (формат слоёв)"
                log("INFO", msg)
                if err:
                    log("INFO", f"первая пропущенная причина: {err}")
                done = True

        if not done:
            log("ERROR", "LoRA не подключилась ни одним способом — кадры выйдут "
                         "без персонажа.")
            log("INFO", "Что делать: проверьте, что файл — LoRA от kohya "
                        "(внутри ключи lora_unet_...lora_down.weight), "
                        "а не полная модель.")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipe = pipe.to(device)
    log("INFO", f"устройство: {device}, режим: {mode}")
    return pipe, mode


def explain_load_error(exc):
    """Переводит падение загрузки модели в короткий человеческий диагноз.

    Человек не обязан разбираться в 70 строках трейсбека huggingface_hub:
    частые причины опознаются по тексту и объясняются сразу с лечением.
    """
    low = (str(exc) + " " + traceback.format_exc()).lower()
    log("ERROR", f"не удалось загрузить модель: {type(exc).__name__}")

    if "offlinemodeisenabled" in low or "offline mode is enabled" in low:
        log("INFO", "Сеть запрещена, а конфигурации SD 1.5 ещё не скачаны в кэш.")
        log("INFO", "Что делать: запустите с включённым интернетом ОДИН раз — "
                    "скачается только конфиг (несколько МБ, не 2 ГБ весов). "
                    "Дальше кэш есть, и работает офлайн.")
    elif "localentrynotfound" in low or "cannot find an appropriate cached snapshot" in low:
        log("INFO", "Конфигурация SD не найдена ни в кэше, ни в сети.")
        log("INFO", "Что делать: включите интернет на один запуск.")
    elif "out of memory" in low or "cublas_status_alloc" in low:
        log("INFO", "Не хватило видеопамяти.")
        log("INFO", "Что делать: уменьшите разрешение до 384x384.")
    elif "cannot find an appropriate format" in low or "unexpected key" in low \
            or "not a valid" in low:
        log("INFO", "Файл модели не читается как SD 1.5: проверьте, что выбран "
                    "именно dreamshaper_8.safetensors, а не LoRA или VAE.")
    else:
        for line in (str(exc) + "\n" + traceback.format_exc()).strip().splitlines()[-5:]:
            log("INFO", "  " + line[:200])


def main():
    ap = argparse.ArgumentParser(description="Генерация кадров спрайта (diffusers)")
    ap.add_argument("--job", default="", help="JSON-файл задания")
    ap.add_argument("--selftest", action="store_true",
                    help="только проверить окружение, ничего не генерировать")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.job:
        log("ERROR", "нужен --job или --selftest")
        return 2

    try:
        with open(args.job, encoding="utf-8") as f:
            job = json.load(f)
    except Exception as e:
        log("ERROR", f"не читается задание: {e}")
        return 2

    try:
        import torch
    except Exception as e:
        log("ERROR", f"в этом python нет torch: {e}")
        return 2
    try:
        import diffusers
    except Exception as e:
        log("ERROR", f"в этом python нет diffusers: {e}")
        return 2

    from PIL import Image

    log("INFO", f"torch {torch.__version__}, diffusers {diffusers.__version__}")
    out_dir = job["out_dir"]
    os.makedirs(out_dir, exist_ok=True)

    try:
        pipe, mode = build_pipeline(job, torch)
    except Exception as e:
        explain_load_error(e)
        return 3

    W = int(job.get("width", 512))
    H = int(job.get("height", 512))
    steps = int(job.get("steps", 24))
    cfg_scale = float(job.get("cfg", 7.0))
    negative = job.get("negative") or None
    device = "cuda" if torch.cuda.is_available() else "cpu"

    init_img = None
    if job.get("init"):
        # convert("RGB") на картинке с прозрачностью даёт под альфой ровно то,
        # что видела kohya при обучении (чёрный) — референс и обучение совпадают
        init_img = Image.open(job["init"]).convert("RGB").resize((W, H), Image.LANCZOS)
        log("INFO", f"референс: {job['init']} -> {W}x{H}")

    total = 0
    for task in job.get("tasks", []):
        prefix = task["prefix"]
        prompt = task["prompt"]
        count = int(task.get("count", 4))
        seed0 = int(task.get("seed", 42))
        s0 = float(task.get("strength", 0.55))
        s1 = task.get("strength_end")
        s1 = s0 if s1 is None else float(s1)

        log("INFO", f"класс {prefix}: {count} кадров, prompt: {prompt}")

        for i in range(count):
            # сила растёт от кадра к кадру: первый ближе к референсу, последний
            # свободнее — иначе все кадры выйдут почти копиями друг друга
            t = 0.0 if count == 1 else i / (count - 1)
            strength = s0 + (s1 - s0) * t
            seed = seed0 + i

            log("FRAME", f"{i + 1}/{count} {prefix} seed={seed} strength={strength:.2f}")

            def cb(p, step, timestep, kw, _i=i, _p=prefix):
                if step % 4 == 0:
                    log("PROGRESS", f"{_i + 1}/{count} {_p} шаг {step}/{steps}")
                return kw

            gen = torch.Generator(device=device).manual_seed(seed)
            params = dict(prompt=prompt, negative_prompt=negative,
                          num_inference_steps=steps, guidance_scale=cfg_scale,
                          generator=gen, callback_on_step_end=cb)
            try:
                if mode == "img2img":
                    params.update(image=init_img, strength=strength,
                                  width=W, height=H)
                else:
                    params.update(width=W, height=H)
                out = pipe(**params)
            except Exception:
                log("ERROR", f"сбой на кадре {i + 1} класса {prefix}")
                print(traceback.format_exc(), flush=True)
                return 4

            path = os.path.join(out_dir, f"{prefix}_{i + 1:04d}.png")
            out.images[0].save(path)
            total += 1
            log("SAVED", path)

    log("DONE", str(total))
    return 0


if __name__ == "__main__":
    sys.exit(main())