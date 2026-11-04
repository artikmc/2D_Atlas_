# -*- coding: utf-8 -*-
"""Окно «ИИ-генерация кадров» — финальный шаг конвейера.

Что делает пользователь:
    1. выбирает картинку-референс (что рисовать);
    2. выбирает персонажа из базы (чьей LoRA это рисовать);
    3. отмечает классы поз и ставит ползунок «кадров на класс»;
    4. «Проверить» — что готово, чего не хватает;
    5. «Сгенерировать» — кадры пишутся в базу;
    6. «Собрать атлас» и «Сохранить атлас» — итоговый PNG.

Своей логики здесь нет: всё в ai_generate.py (PIL, база) и sd_generate.py
(сама нейросеть в venv kohya). Окно собирает поля, запускает поток и печатает лог.
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import ai_generate as ag

# Пути по умолчанию — те, что уже используются обучением (train_window.py).
DEFAULT_MODEL = r"G:/models/dreamshaper_8.safetensors"
DEFAULT_KOHYA = r"G:/kohya_ss"
DEFAULT_OUTPUT = "output"


class GenerateWindow:
    def __init__(self, parent, db_path="atlas_database.db"):
        self.parent = parent
        self.db_path = db_path
        self.worker = None
        self.stop_flag = False
        self.queue = queue.Queue()
        self.atlas = None          # последний собранный атлас (PIL.Image)
        self.atlas_stat = []
        self.last_run_dir = None   # папка прогона: там job.json и PNG

        self.window = tk.Toplevel(parent)
        self.window.title("Модуль ИИ — генерация кадров")
        self.window.geometry("980x780")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self._build_top()
        self._build_poses()
        self._build_params()
        self._build_buttons()
        self._build_log()

        self.reload_characters()
        self.write("Генерация кадров: референс + LoRA персонажа -> кадры в базу -> атлас.")
        self.write("1) выберите референс и персонажа;  2) отметьте классы;")
        self.write("3) «Проверить»;  4) «Сгенерировать»;  5) «Собрать атлас».\n")
        self.check_quick()

    # ------------------------------------------------------------------ UI
    def _build_top(self):
        src = tk.LabelFrame(self.window, text="Источник")
        src.pack(fill=tk.X, padx=10, pady=(10, 4))
        src.columnconfigure(1, weight=1)

        tk.Label(src, text="Референс (картинка):").grid(row=0, column=0, sticky="w",
                                                        padx=(6, 4), pady=2)
        self.var_ref = tk.StringVar()
        tk.Entry(src, textvariable=self.var_ref).grid(row=0, column=1, sticky="we", pady=2)
        tk.Button(src, text="...", width=3, command=self.pick_reference).grid(
            row=0, column=2, padx=(4, 6), pady=2)

        tk.Label(src, text="Персонаж из базы:").grid(row=1, column=0, sticky="w",
                                                      padx=(6, 4), pady=2)
        self.var_char = tk.StringVar()
        self.cmb_char = ttk.Combobox(src, textvariable=self.var_char, state="readonly")
        self.cmb_char.grid(row=1, column=1, sticky="we", pady=2)
        self.cmb_char.bind("<<ComboboxSelected>>", lambda e: self.on_character_change())
        tk.Button(src, text="Обновить", command=self.reload_characters).grid(
            row=1, column=2, padx=(4, 6), pady=2)

        tk.Label(src, text="База данных:").grid(row=2, column=0, sticky="w",
                                                 padx=(6, 4), pady=2)
        self.lbl_db = tk.Label(src, text=os.path.abspath(self.db_path), anchor="w",
                               fg="#444444")
        self.lbl_db.grid(row=2, column=1, columnspan=2, sticky="we", pady=2)

    def _build_poses(self):
        box = tk.LabelFrame(self.window, text="Кадры")
        box.pack(fill=tk.X, padx=10, pady=4)

        # слева: список классов с галочками
        left = tk.Frame(box)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)

        tk.Label(left, text="Классы поз (из базы):", anchor="w").pack(anchor="w")
        list_wrap = tk.Frame(left)
        list_wrap.pack(fill=tk.BOTH, expand=True)

        self.lst_classes = tk.Listbox(list_wrap, selectmode=tk.MULTIPLE, height=6,
                                      exportselection=False, activestyle="dotbox")
        sc = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=self.lst_classes.yview)
        self.lst_classes.configure(yscrollcommand=sc.set)
        self.lst_classes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)

        row = tk.Frame(left)
        row.pack(fill=tk.X, pady=(4, 0))
        tk.Button(row, text="Все", command=self.select_all_classes).pack(side=tk.LEFT)
        tk.Button(row, text="Ни одного", command=self.select_no_classes).pack(
            side=tk.LEFT, padx=(4, 0))

        # справа: ползунок и подпись «сколько получится»
        right = tk.Frame(box, width=250)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=6)
        right.pack_propagate(False)

        self.var_count = tk.IntVar(value=4)
        self.scale_count = tk.Scale(right, from_=1, to=12, orient=tk.HORIZONTAL,
                                    label="Кадров на класс", variable=self.var_count,
                                    command=lambda v: self.update_estimate())
        self.scale_count.pack(fill=tk.X)

        self.lbl_est = tk.Label(right, text="", anchor="w", fg="#005500",
                                justify="left", wraplength=240)
        self.lbl_est.pack(fill=tk.X, pady=(4, 0))
        self.lst_classes.bind("<<ListboxSelect>>", lambda e: self.update_estimate())

    def _build_params(self):
        box = tk.LabelFrame(self.window, text="Модель и параметры")
        box.pack(fill=tk.X, padx=10, pady=4)

        box.columnconfigure(1, weight=1)
        box.columnconfigure(4, weight=1)

        self.var_model = tk.StringVar(value=DEFAULT_MODEL)
        self.var_lora = tk.StringVar()
        self.var_kohya = tk.StringVar(value=DEFAULT_KOHYA)
        self.var_trigger = tk.StringVar(value="")
        self.var_extra = tk.StringVar(value="")
        self.var_negative = tk.StringVar(value=ag.DEFAULT_NEGATIVE)

        self._path_row(box, 0, 0, "Базовая модель:", self.var_model, "file")
        self._path_row(box, 0, 3, "LoRA персонажа:", self.var_lora, "file")
        self._path_row(box, 1, 0, "Папка kohya_ss:", self.var_kohya, "dir")

        tk.Label(box, text="Триггер LoRA:").grid(row=1, column=3, sticky="w",
                                                  padx=(10, 4), pady=2)
        tk.Entry(box, textvariable=self.var_trigger, width=14).grid(
            row=1, column=4, sticky="w", pady=2)

        tk.Label(box, text="Доп. теги:").grid(row=2, column=0, sticky="w",
                                               padx=(6, 4), pady=2)
        tk.Entry(box, textvariable=self.var_extra).grid(row=2, column=1, columnspan=4,
                                                         sticky="we", pady=2, padx=(0, 6))

        # числовые параметры в одну строку
        nums = tk.Frame(box)
        nums.grid(row=3, column=0, columnspan=5, sticky="we", padx=6, pady=(6, 6))

        self.var_steps = tk.StringVar(value="24")
        self.var_cfg = tk.StringVar(value="7.0")
        self.var_scale = tk.StringVar(value="1.0")
        self.var_s0 = tk.StringVar(value="0.45")
        self.var_s1 = tk.StringVar(value="0.70")

        for i, (label, var, w) in enumerate((
                ("Шагов:", self.var_steps, 5),
                ("CFG:", self.var_cfg, 5),
                ("Сила LoRA:", self.var_scale, 5),
                ("Strength от:", self.var_s0, 5),
                ("Strength до:", self.var_s1, 5))):
            tk.Label(nums, text=label).grid(row=0, column=i * 2, sticky="w",
                                             padx=(0 if i == 0 else 10, 3))
            tk.Entry(nums, textvariable=var, width=w).grid(row=0, column=i * 2 + 1,
                                                           sticky="w")

        tk.Label(nums, text="Негатив:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        tk.Entry(nums, textvariable=self.var_negative).grid(
            row=1, column=1, columnspan=7, sticky="we", pady=(6, 0))

        # замена кадров в базе — по умолчанию ВЫКЛЮЧЕНА: старые кадры
        # персонажа — единственный экземпляр его анимаций, терять их без спроса нельзя
        self.var_replace = tk.BooleanVar(value=False)
        tk.Checkbutton(nums, text="Заменить прежние кадры этих классов",
                       variable=self.var_replace, fg="#8a4b00").grid(
            row=2, column=0, columnspan=10, sticky="w", pady=(6, 0))

        # сеть по умолчанию РАЗРЕШЕНА: from_single_file догружает из кэша HF
        # конфиги архитектуры SD, которых нет в .safetensors. Офлайн имеет смысл
        # ставить только когда конфиги уже скачаны (скажет «Проверить движок»).
        self.var_offline = tk.BooleanVar(value=False)
        tk.Checkbutton(nums, text="Без интернета (только если конфиг SD уже в кэше)",
                       variable=self.var_offline, fg="#666666").grid(
            row=3, column=0, columnspan=10, sticky="w")

    def _path_row(self, parent, row, col, label, var, kind):
        tk.Label(parent, text=label).grid(row=row, column=col, sticky="w",
                                           padx=(6, 4), pady=2)
        tk.Entry(parent, textvariable=var).grid(row=row, column=col + 1,
                                                 columnspan=2, sticky="we", pady=2)

        def pick():
            if kind == "dir":
                p = filedialog.askdirectory(parent=self.window)
            else:
                p = filedialog.askopenfilename(
                    parent=self.window,
                    filetypes=[("safetensors", "*.safetensors"), ("Все файлы", "*.*")])
            if p:
                var.set(p)

        tk.Button(parent, text="...", width=3, command=pick).grid(
            row=row, column=col + 3, padx=(4, 6) if col == 0 else (4, 0), pady=2)

    def _build_buttons(self):
        bar = tk.Frame(self.window)
        bar.pack(fill=tk.X, padx=10, pady=4)

        self.btn_check = tk.Button(bar, text="Проверить", command=self.do_check)
        self.btn_check.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_env = tk.Button(bar, text="Проверить движок", command=self.do_env_check)
        self.btn_env.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_gen = tk.Button(bar, text="Сгенерировать", command=self.do_generate,
                                 bg="#d8f0d8")
        self.btn_gen.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_stop = tk.Button(bar, text="Остановить", command=self.do_stop,
                                  state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_atlas = tk.Button(bar, text="Собрать атлас", command=self.do_build_atlas)
        self.btn_atlas.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_save = tk.Button(bar, text="Сохранить атлас...", command=self.do_save_atlas,
                                  state=tk.DISABLED)
        self.btn_save.pack(side=tk.LEFT, padx=(0, 6))

        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=110)
        self.progress.pack(side=tk.LEFT, padx=6)

        tk.Button(bar, text="Копировать лог", command=self.do_copy_log).pack(
            side=tk.RIGHT, padx=(6, 0))
        tk.Button(bar, text="Лог в файл...", command=self.do_save_log).pack(
            side=tk.RIGHT, padx=(6, 0))
        self.btn_close = tk.Button(bar, text="Закрыть", command=self.close)
        self.btn_close.pack(side=tk.RIGHT, padx=(6, 0))

    def _build_log(self):
        wrap = tk.Frame(self.window)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.log = tk.Text(wrap, wrap="word", height=16, bg="white")
        sc = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=sc.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(state="disabled")

        self.log_menu = tk.Menu(self.log, tearoff=0)
        self.log_menu.add_command(label="Копировать всё", command=self.do_copy_log)
        self.log_menu.add_command(label="Выделить всё", command=self.do_select_all)
        self.log_menu.add_separator()
        self.log_menu.add_command(label="Сохранить в файл...", command=self.do_save_log)
        self.log.bind("<Button-3>", self._show_log_menu)
        self.log.bind("<Control-a>", lambda e: (self.do_select_all(), "break")[1])

    # ------------------------------------------------------- данные и оценка
    def reload_characters(self):
        """Перечитывает персонажей из базы."""
        try:
            chars = ag.list_characters(self.db_path)
        except Exception as e:
            self.write(f"НЕТ: база не читается — {e}")
            return
        if not chars:
            self.write("НЕТ: в базе нет персонажей (таблица characters пуста)")
            return
        self._chars = chars
        names = [f"{name} (id {cid})" for cid, name in chars]
        self._char_ids = [cid for cid, _ in chars]
        self.cmb_char["values"] = names
        if names and not self.var_char.get():
            self.cmb_char.current(0)
            self.var_char.set(names[0])
        self.on_character_change()

    def select_character_id(self):
        """id выбранного персонажа или None.

        Берём из индекса списка, а не разбором подписи: подпись — это текст,
        который зависит от шрифта и перевода, и сравнивать его ненадёжно.
        """
        ids = getattr(self, "_char_ids", [])
        if not ids:
            return None
        idx = self.cmb_char.current()
        if isinstance(idx, int) and 0 <= idx < len(ids):
            return ids[idx]
        return None

    def on_character_change(self):
        """Подтягивает классы персонажа и предлагает LoRA по имени.

        Вызывается и после ручной смены персонажа в списке: тогда подпись в
        поле и current() уже согласованы.
        """
        cid = self.select_character_id()
        self.lst_classes.delete(0, tk.END)
        if cid is None:
            self.update_estimate()
            return
        try:
            classes = ag.list_pose_classes(self.db_path, cid)
        except Exception as e:
            self.write(f"НЕТ: классы не прочитались — {e}")
            classes = []
        for c in classes:
            self.lst_classes.insert(tk.END, c)
        self.select_all_classes()

        # триггер и LoRA: имя персонажа латиницей + id, как в dataset_export
        name = next((n for i, n in getattr(self, "_chars", []) if i == cid), "")
        if name:
            trig = "".join(ch for ch in ag.transliterate(name) if ch.isalnum())
            self.var_trigger.set(f"{trig}{cid}" if trig else f"char{cid}")
        if not self.var_lora.get() and name:
            guess = os.path.join(DEFAULT_OUTPUT, f"{self.var_trigger.get() or 'lora'}_lora.safetensors")
            if os.path.isfile(guess):
                self.var_lora.set(os.path.abspath(guess))
        self.update_estimate()

    def select_all_classes(self):
        self.lst_classes.select_set(0, tk.END)
        self.update_estimate()

    def select_no_classes(self):
        self.lst_classes.select_clear(0, tk.END)
        self.update_estimate()

    def selected_classes(self):
        return [self.lst_classes.get(i) for i in self.lst_classes.curselection()]

    def update_estimate(self):
        """Показывает, сколько кадров получится и сколько это примерно времени."""
        n = len(self.selected_classes())
        try:
            per = int(self.var_count.get())
        except Exception:
            per = 0
        total = n * per
        if total == 0:
            self.lbl_est.config(text="кадров не выбрано", fg="#aa0000")
            return
        # на 3050 кадр 512x512/24 шага — примерно 8-14 с; берём 11 с как среднее
        secs = total * 11 + 40          # + загрузка модели
        self.lbl_est.config(
            text=f"{n} класс(ов) × {per} = {total} кадров\n≈ {secs // 60} мин {secs % 60} с",
            fg="#005500" if total <= 60 else "#aa6600")

    # ------------------------------------------------------------- проверка
    def check_quick(self):
        """Короткая проверка при открытии: то, что видно без запуска torch."""
        problems = []
        if not ag.list_characters(self.db_path):
            problems.append("в базе нет персонажей")
        py = ag.find_python(self.var_kohya.get().strip())
        if not py:
            problems.append("не найден python в venv kohya_ss")
        if not os.path.isfile(self.var_model.get().strip()):
            problems.append("не найдена базовая модель")
        for p in problems:
            self.write(f"ВНИМАНИЕ: {p}")

    def do_check(self):
        """Полная проверка: файлы, LoRA, python, torch/diffusers, классы."""
        self.write("\n— проверка —")
        ok = True

        py = ag.find_python(self.var_kohya.get().strip())
        if py:
            self.write(f"  ОК: python — {py}")
        else:
            self.write("  НЕТ: в папке kohya_ss нет venv (ожидался venv/Scripts/python.exe)")
            ok = False

        model = self.var_model.get().strip()
        if os.path.isfile(model):
            gb = os.path.getsize(model) / 1024 ** 3
            self.write(f"  ОК: модель {os.path.basename(model)} ({gb:.2f} ГБ)")
            if gb < 1.5:
                self.write("  ВНИМАНИЕ: меньше 1.5 ГБ — похоже, это не полная SD 1.5")
        else:
            self.write(f"  НЕТ: модель не найдена: {model}")
            ok = False

        lora = self.var_lora.get().strip()
        if lora and os.path.isfile(lora):
            mb = os.path.getsize(lora) / 1024 ** 2
            self.write(f"  ОК: LoRA {os.path.basename(lora)} ({mb:.1f} МБ)")
        elif lora:
            self.write(f"  НЕТ: LoRA не найдена: {lora}")
            ok = False
        else:
            self.write("  ВНИМАНИЕ: LoRA не указана — рисовать будет базовая модель "
                       "(сходство с персонажем пропадёт)")

        ref = self.var_ref.get().strip()
        if ref and os.path.isfile(ref):
            try:
                from PIL import Image
                self.write(f"  ОК: референс {os.path.basename(ref)} "
                           f"{Image.open(ref).size}")
            except Exception as e:
                self.write(f"  НЕТ: референс не читается — {e}")
                ok = False
        else:
            self.write("  НЕТ: референс не выбран")
            ok = False

        cid = self.select_character_id()
        if cid is None:
            self.write("  НЕТ: персонаж не выбран")
            ok = False
        else:
            classes = self.selected_classes()
            self.write(f"  ОК: персонаж id {cid}, отмечено классов: {len(classes)}")
            if not classes:
                self.write("  НЕТ: не отмечен ни один класс")
                ok = False

        if not self.db_path or not os.path.isfile(self.db_path):
            self.write(f"  НЕТ: база не найдена: {self.db_path}")
            ok = False

        self.write("ИТОГ: " + ("можно генерировать" if ok
                               else "есть НЕТ — см. выше"))

    # ------------------------------------------------------------ генерация
    def collect_job(self):
        """Собирает job для sd_generate.py. Ошибки — ValueError с текстом."""
        ref = self.var_ref.get().strip()
        if not ref or not os.path.isfile(ref):
            raise ValueError("не выбран файл референса")
        model = self.var_model.get().strip()
        if not os.path.isfile(model):
            raise ValueError("не найдена базовая модель")
        cid = self.select_character_id()
        if cid is None:
            raise ValueError("не выбран персонаж")
        classes = self.selected_classes()
        if not classes:
            raise ValueError("не отмечен ни один класс")

        try:
            count = int(self.var_count.get())
            steps = int(self.var_steps.get())
            cfg_scale = float(self.var_cfg.get())
            lscale = float(self.var_scale.get())
            s0 = float(self.var_s0.get())
            s1 = float(self.var_s1.get())
        except ValueError as e:
            raise ValueError(f"проверьте числа в параметрах ({e})") from e

        if not (0 < s0 <= 1 and 0 < s1 <= 1):
            raise ValueError("strength должен быть в диапазоне 0..1")

        trigger = self.var_trigger.get().strip() or f"char{cid}"
        out_dir = os.path.join(DEFAULT_OUTPUT, "ai_frames", ag.timestamp())

        # префикс файла должен быть уникален для класса: два разных класса
        # («Стояние» и «стояние») дают одно слово standing и без индекса
        # перезаписали бы друг друга в одной папке
        tasks, mapping = [], {}
        for i, cls in enumerate(classes):
            prefix = f"{i:02d}_{ag.pose_word(cls)}"
            tasks.append({
                "prefix": prefix,
                "prompt": ag.build_prompt(trigger, cls, self.var_extra.get()),
                "count": count,
                "seed": 42,
                "strength": s0,
                "strength_end": s1,
            })
            mapping[prefix] = cls

        return ag.make_job(
            model=model, lora=self.var_lora.get().strip(), lora_scale=lscale,
            kohya_root=self.var_kohya.get().strip(), out_dir=out_dir, tasks=tasks,
            init=ref, steps=steps, cfg=cfg_scale,
            negative=self.var_negative.get().strip()) | {
            "_classes": mapping,
            "_character_id": cid,
        }

    def do_generate(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            job = self.collect_job()
        except ValueError as e:
            messagebox.showwarning("Не хватает данных", str(e), parent=self.window)
            return

        py = ag.find_python(self.var_kohya.get().strip())
        if not py:
            messagebox.showerror("Нет python",
                                 "В папке kohya_ss не найден venv.\n"
                                 "Укажите папку, где лежит venv\\Scripts\\python.exe.",
                                 parent=self.window)
            return

        self.stop_flag = False
        self._busy(True)
        self.write("\n— генерация —")
        self.write(f"кадров: {sum(t['count'] for t in job['tasks'])}, "
                   f"классов: {len(job['tasks'])}, папка: {job['out_dir']}")

        self.worker = threading.Thread(target=self._gen_thread, args=(py, job),
                                       daemon=True)
        self.worker.start()
        self.window.after(120, self._poll)

    def _gen_thread(self, py, job):
        """Тело потока: подготовка референса, запуск sd_generate.py, разбор лога."""
        try:
            os.makedirs(job["out_dir"], exist_ok=True)

            # референс готовим здесь (системный PIL): чёрный фон, спрайт по центру
            ref_path = os.path.join(job["out_dir"], "reference.png")
            ag.prepare_reference(self.var_ref.get().strip()).save(ref_path)
            job["init"] = os.path.abspath(ref_path)
            job_path = ag.save_job({k: v for k, v in job.items()
                                    if not k.startswith("_")}, job["out_dir"])
            self.queue.put(("line", f"  референс подготовлен: {ref_path}"))

            script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "sd_generate.py")
            if not os.path.isfile(script):
                self.queue.put(("line", f"ERROR нет файла {script}"))
                self.queue.put(("done", 1))
                return

            saved = []
            code = ag.run_generation(
                py, script, job_path,
                on_line=lambda s: self.queue.put(("line", self._pretty(s, saved))),
                should_stop=lambda: self.stop_flag,
                offline=bool(self.var_offline.get()))

            if code != 0:
                self.queue.put(("line", f"  генерация завершилась с кодом {code}"))
                self.queue.put(("fail", code))
                return

            # кадры: вырезаем фон, вписываем в клетку и пишем в базу
            self.queue.put(("line", f"  кадров получено: {len(saved)}"))
            self.queue.put(("line", "  вырезаю фон и пишу в базу..."))
            cells, written = self._import_frames(saved, job)
            self.queue.put(("line", f"  записано в базу: {written} кадров"))
            self.queue.put(("line", f"  клетка атласа: {cells}"))
            self.queue.put(("ok", (written, job["out_dir"])))
        except Exception as e:
            self.queue.put(("line", f"ERROR {type(e).__name__}: {e}"))
            self.queue.put(("fail", 1))

    def _pretty(self, line, saved):
        """Убирает служебный префикс и запоминает пути сохранённых кадров."""
        for kind in ("INFO", "FRAME", "PROGRESS", "SAVED", "DONE", "ERROR"):
            if line.startswith(kind + " "):
                rest = line[len(kind) + 1:]
                if kind == "SAVED":
                    saved.append(rest)
                    return f"  сохранён: {os.path.basename(rest)}"
                if kind == "ERROR":
                    return f"ОШИБКА: {rest}"
                if kind == "DONE":
                    return f"  модель закончила: {rest} кадров"
                if kind == "PROGRESS":
                    return f"    {rest}"
                return f"  {rest}"
        return "  " + line

    def _import_frames(self, saved, job):
        """Вырезает фон у файлов, вписывает в клетку, пишет в базу."""
        from PIL import Image
        conn = ag.connect(self.db_path)
        try:
            cell = ag.sprite_size_of_character(conn, job["_character_id"])
        finally:
            conn.close()

        by_prefix = {}
        for path in saved:
            prefix = os.path.basename(path).rsplit("_", 1)[0]
            try:
                img = Image.open(path)
            except Exception as e:
                self.queue.put(("line", f"  пропущен {os.path.basename(path)}: {e}"))
                continue
            cut = ag.cut_background(img)
            by_prefix.setdefault(prefix, []).append(ag.to_cell(cut, cell[0], cell[1]))

        class_frames = {}
        for prefix, imgs in by_prefix.items():
            ru = job["_classes"].get(prefix, prefix)
            class_frames[ru] = imgs

        # замена прежних кадров — только по галочке пользователя:
        # без неё старые кадры сохраняются, новые дописываются
        replace = bool(self.var_replace.get())
        written, warns = ag.write_frames(
            self.db_path, job["_character_id"], class_frames, cell_size=None,
            replace=replace)
        if not replace:
            self.queue.put(("line", "  прежние кадры сохранены (замена выключена)"))
        for w in warns:
            self.queue.put(("line", f"  {w}"))
        return f"{cell[0]}x{cell[1]}", written

    def _poll(self):
        """Забирает сообщения потока в GUI-потоке."""
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "line":
                    self.write(payload)
                elif kind == "ok":
                    written, out_dir = payload
                    if out_dir:
                        self.last_run_dir = out_dir
                        self.write(f"ГОТОВО: {written} кадров в базе. Теперь «Собрать атлас».")
                        self._refresh_after_generation()
                    self._busy(False)
                    return
                elif kind == "fail":
                    self.write("НЕ УДАЛОСЬ. Смотрите ОШИБКА выше.")
                    self._busy(False)
                    return
        except queue.Empty:
            pass
        if self.worker and self.worker.is_alive():
            self.window.after(120, self._poll)
        else:
            # поток кончился, а сообщений не осталось — снимаем блокировку
            self._busy(False)

    def _refresh_after_generation(self):
        """После записи перечитывает классы: новые могли появиться."""
        cid = self.select_character_id()
        if cid is None:
            return
        try:
            classes = ag.list_pose_classes(self.db_path, cid)
        except Exception:
            return
        current = set(self.selected_classes())
        self.lst_classes.delete(0, tk.END)
        for c in classes:
            self.lst_classes.insert(tk.END, c)
        for i, c in enumerate(classes):
            if c in current:
                self.lst_classes.select_set(i)
        self.update_estimate()
        self.btn_atlas.config(state=tk.NORMAL)

    def _env_thread(self, py):
        """Запускает самопроверку воркера и переводит её в лог."""
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "sd_generate.py")
        if not os.path.isfile(script):
            self.write(f"  НЕТ: нет файла {script}")
            self._busy(False)
            return
        code = ag.run_selftest(
            py, script,
            on_line=lambda s: self.queue.put(("line", self._pretty(s, []))),
            kohya_root=self.var_kohya.get().strip())
        # Контракт: 0 — окружение готово, 2 — движок не работает.
        # Раньше код 1 означал «нет конфига в кэше», а окно выдавало его за
        # отсутствие CUDA. Теперь о CUDA сообщает сам воркер, а окно только
        # подводит итог — без догадок о причине.
        if code == 0:
            self.queue.put(("line", "ИТОГ: движок готов к генерации (подробности выше)"))
        elif code == 2:
            self.queue.put(("line", "ИТОГ: движок не запустится — причина в ошибке выше"))
        else:
            self.queue.put(("line", f"  самопроверка завершилась с кодом {code}"))
        self.queue.put(("line", "  Готово."))
        self.queue.put(("ok", (0, None)))

    def do_env_check(self):
        """Самопроверка самого движка: torch, CUDA, diffusers, токенизатор."""
        if self.worker and self.worker.is_alive():
            return
        self.write("\n— самопроверка движка (несколько секунд) —")
        py = ag.find_python(self.var_kohya.get().strip())
        if not py:
            self.write("  НЕТ: в папке kohya_ss не найден venv — "
                       "указать её нужно в поле «Папка kohya_ss»")
            return
        self._busy(True)
        self.worker = threading.Thread(target=self._env_thread, args=(py,), daemon=True)
        self.worker.start()
        self.window.after(120, self._poll)

    def do_stop(self):
        self.stop_flag = True
        self.write("  останавливаю после текущего шага...")

    # --------------------------------------------------------------- атлас
    def do_build_atlas(self):
        cid = self.select_character_id()
        if cid is None:
            messagebox.showwarning("Атлас", "Сначала выберите персонажа.", parent=self.window)
            return
        classes = self.selected_classes() or None
        try:
            atlas, stat = ag.build_atlas(self.db_path, cid, classes)
        except Exception as e:
            messagebox.showerror("Атлас", f"Не собрался: {e}", parent=self.window)
            return
        self.atlas = atlas
        self.atlas_stat = stat
        self.write(f"\n— атлас —")
        self.write(f"  размер: {atlas.width}x{atlas.height}, рядов: {len(stat)}")
        for cls, n in stat:
            self.write(f"    {cls}: {n} кадров")

        # предпросмотр в отдельном окне — сразу видно, что получилось
        self._show_preview(atlas)
        self.btn_save.config(state=tk.NORMAL)

    def _show_preview(self, atlas):
        """Окно предпросмотра атласа. Масштаб — целыми пикселями, без сглаживания."""
        from PIL import ImageTk
        win = tk.Toplevel(self.window)
        win.title(f"Атлас {atlas.width}x{atlas.height}")
        win.transient(self.window)

        screen_w = win.winfo_screenwidth() - 80
        screen_h = win.winfo_screenheight() - 160
        zoom = max(1, min(screen_w // max(1, atlas.width),
                          screen_h // max(1, atlas.height), 6))
        big = atlas.resize((atlas.width * zoom, atlas.height * zoom), 0)  # NEAREST
        photo = ImageTk.PhotoImage(big)

        canvas = tk.Canvas(win, width=big.width, height=big.height,
                           bg="#3a3a3a", highlightthickness=0)
        canvas.pack(padx=6, pady=6)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo          # держим ссылку, иначе Tk удалит картинку

        tk.Label(win, text=f"увеличение {zoom}x, {len(self.atlas_stat)} рядов",
                 anchor="w").pack(fill=tk.X, padx=6, pady=(0, 6))

    def do_save_atlas(self):
        if self.atlas is None:
            return
        cid = self.select_character_id()
        name = next((n for i, n in getattr(self, "_chars", []) if i == cid), "atlas")
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "atlas"
        default = f"atlas_{safe}_{ag.timestamp()}.png"
        path = filedialog.asksaveasfilename(
            parent=self.window, title="Сохранить атлас", initialfile=default,
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("Все файлы", "*.*")])
        if not path:
            return
        try:
            ag.save_atlas(self.atlas, path)
        except Exception as e:
            messagebox.showerror("Атлас", f"Не сохранился: {e}", parent=self.window)
            return
        self.write(f"  атлас сохранён: {os.path.abspath(path)}")

    # ---------------------------------------------------------------- прочее
    def pick_reference(self):
        path = filedialog.askopenfilename(
            parent=self.window, title="Выберите референс",
            filetypes=[("Картинки", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                       ("Все файлы", "*.*")])
        if path:
            self.var_ref.set(path)
            self.write(f"  референс: {path}")

    def write(self, text):
        self.log.configure(state="normal")
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def log_text(self):
        return self.log.get("1.0", tk.END).rstrip("\n")

    def _show_log_menu(self, event):
        try:
            self.log_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.log_menu.grab_release()

    def do_select_all(self):
        self.log.tag_add(tk.SEL, "1.0", tk.END)
        self.log.mark_set(tk.INSERT, "1.0")
        self.log.see("1.0")

    def do_copy_log(self):
        text = self.log_text()
        if not text.strip():
            self.write("  лог пуст — копировать нечего")
            return
        try:
            self.window.clipboard_clear()
            self.window.clipboard_append(text)
            self.window.update_idletasks()
        except tk.TclError as e:
            self.write(f"  не удалось скопировать: {e}")
            return
        self.write(f"  лог скопирован ({len(text)} символов)")

    def do_save_log(self):
        text = self.log_text()
        if not text.strip():
            self.write("  лог пуст — сохранять нечего")
            return
        path = filedialog.asksaveasfilename(
            parent=self.window, title="Сохранить лог",
            initialfile=f"generate_log_{ag.timestamp()}.txt",
            defaultextension=".txt",
            filetypes=[("Текст", "*.txt"), ("Все файлы", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
                f.write(text + "\n")
        except OSError as e:
            self.write(f"  не удалось сохранить: {e}")
            return
        self.write(f"  лог сохранён: {os.path.abspath(path)}")

    def _busy(self, on):
        for b in (self.btn_check, self.btn_env, self.btn_gen, self.btn_atlas, self.btn_close):
            b.config(state=tk.DISABLED if on else tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL if on else tk.DISABLED)
        if on:
            self.progress.start(12)
        else:
            self.progress.stop()

    def close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Идёт генерация",
                                       "Остановить и закрыть окно?",
                                       parent=self.window):
                return
            self.stop_flag = True
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()