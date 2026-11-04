# -*- coding: utf-8 -*-
"""Окно «Обучение LoRA» — то, что открывается кнопкой в модуле ИИ.

Своей логики здесь почти нет: все расчёты и запуск живут в lora_train.py.
Окно только показывает поля, зовёт функции и печатает лог.

Окно модальное (grab_set), как EnhanceWindow в проекте.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import lora_train as lt


class TrainWindow:
    def __init__(self, parent, dataset_root="dataset"):
        """Настройки и запуск обучения LoRA на kohya_ss."""
        self.parent = parent
        self.worker = None
        self.stop_flag = False

        self.window = tk.Toplevel(parent)
        self.window.title("Обучение LoRA")
        self.window.geometry("860x680")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        # ---------- данные ----------
        data = tk.LabelFrame(self.window, text="Данные")
        data.pack(fill=tk.X, padx=10, pady=(10, 4))
        data.columnconfigure(1, weight=1)

        self.var_dataset = tk.StringVar(value=dataset_root)
        self._row(data, 0, "Папка датасета:", self.var_dataset, kind="dir")

        self.var_model = tk.StringVar()
        self._row(data, 1, "Базовая модель (SD 1.5):", self.var_model, kind="file")

        self.var_kohya = tk.StringVar(value="kohya_ss")
        self._row(data, 2, "Папка kohya_ss:", self.var_kohya, kind="dir")

        self.var_output = tk.StringVar(value="output")
        self._row(data, 3, "Куда сохранить LoRA:", self.var_output, kind="dir")

        self.var_name = tk.StringVar(value="man18_lora")
        self._row(data, 4, "Имя файла LoRA:", self.var_name, kind="text")

        # ---------- параметры ----------
        params = tk.LabelFrame(self.window, text="Параметры обучения (пресет RTX 3050 8 ГБ)")
        params.pack(fill=tk.X, padx=10, pady=4)

        # слева и справа по 3 поля, чтобы не растягивать окно в высоту
        left = tk.Frame(params)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0), pady=6)
        right = tk.Frame(params)
        right.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=6)

        p = lt.PRESET_3050
        self.var_res = tk.StringVar(value=p["resolution"])
        self.var_dim = tk.StringVar(value=str(p["network_dim"]))
        self.var_alpha = tk.StringVar(value=str(p["network_alpha"]))
        self.var_epochs = tk.StringVar(value=str(p["max_train_epochs"]))
        self.var_batch = tk.StringVar(value=str(p["train_batch_size"]))
        self.var_repeats = tk.StringVar(value="1")
        self.var_lr = tk.StringVar(value=str(p["learning_rate"]))

        self._mini(left, 0, "Разрешение:", self.var_res)
        self._mini(left, 1, "network_dim:", self.var_dim)
        self._mini(left, 2, "network_alpha:", self.var_alpha)
        self._mini(left, 3, "learning rate:", self.var_lr)

        self._mini(right, 0, "Эпох:", self.var_epochs)
        self._mini(right, 1, "batch size:", self.var_batch)
        self._mini(right, 2, "повторов (repeats):", self.var_repeats)

        # пересчёт шагов при изменении эпох/повторов/батча
        for v in (self.var_epochs, self.var_repeats, self.var_batch):
            v.trace_add("write", lambda *a: self.update_steps())

        self.lbl_steps = tk.Label(right, text="", anchor="w", fg="#005500")
        self.lbl_steps.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        right.columnconfigure(1, weight=1)

        # ---------- кнопки ----------
        btns = tk.Frame(self.window)
        btns.pack(fill=tk.X, padx=10, pady=6)

        self.btn_check = tk.Button(btns, text="Проверить готовность", command=self.do_check)
        self.btn_check.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_cuda = tk.Button(btns, text="Проверить CUDA", command=self.do_cuda)
        self.btn_cuda.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_cfg = tk.Button(btns, text="Сохранить конфиг", command=self.do_save_config)
        self.btn_cfg.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_train = tk.Button(btns, text="Начать обучение", command=self.do_train,
                                   bg="#d8f0d8")
        self.btn_train.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_stop = tk.Button(btns, text="Остановить", command=self.do_stop,
                                  state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 6))

        self.progress = ttk.Progressbar(btns, mode="indeterminate", length=120)
        self.progress.pack(side=tk.LEFT, padx=6)

        self.btn_close = tk.Button(btns, text="Закрыть", command=self.close)
        self.btn_close.pack(side=tk.RIGHT)

        # копирование лога остаётся доступным даже во время работы
        self.btn_copy = tk.Button(btns, text="Копировать лог", command=self.do_copy_log)
        self.btn_copy.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_logfile = tk.Button(btns, text="Лог в файл...", command=self.do_save_log)
        self.btn_logfile.pack(side=tk.RIGHT, padx=(6, 0))

        # ---------- лог ----------
        log_wrap = tk.Frame(self.window)
        log_wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.log = tk.Text(log_wrap, wrap="word", height=16, bg="white")
        sc = ttk.Scrollbar(log_wrap, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=sc.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(state="disabled")

        # правый клик в логе — те же действия, что кнопками
        self.log_menu = tk.Menu(self.log, tearoff=0)
        self.log_menu.add_command(label="Копировать всё", command=self.do_copy_log)
        self.log_menu.add_command(label="Выделить всё", command=self.do_select_all)
        self.log_menu.add_separator()
        self.log_menu.add_command(label="Сохранить в файл...", command=self.do_save_log)
        self.log.bind("<Button-3>", self._show_log_menu)
        self.log.bind("<Control-a>", lambda e: (self.do_select_all(), "break")[1])

        self.write("Обучение LoRA через kohya_ss.")
        self.write("1) укажите базовую модель .safetensors (SD 1.5) и папку kohya_ss;")
        self.write("2) «Проверить готовность» — покажет, чего не хватает;")
        self.write("3) «Сохранить конфиг» — создаст .toml, его можно открыть и в GUI kohya;")
        self.write("4) «Начать обучение» — запустит и покажет лог по строкам.\n")

        self.update_steps()

    # ---------- мелкие помощники построения ----------
    def _row(self, parent, row, label, var, kind="text"):
        """Строка «подпись + поле + кнопка выбора»."""
        tk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(6, 4), pady=2)
        tk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="we", pady=2)

        def pick():
            if kind == "dir":
                path = filedialog.askdirectory(parent=self.window)
            else:
                path = filedialog.askopenfilename(
                    parent=self.window, filetypes=[("safetensors", "*.safetensors"),
                                                   ("Все файлы", "*.*")])
            if path:
                var.set(path)

        tk.Button(parent, text="...", width=3, command=pick).grid(row=row, column=2,
                                                                  padx=(4, 6), pady=2)

    def _mini(self, parent, row, label, var):
        tk.Label(parent, text=label, anchor="w").grid(row=row, column=0, sticky="w", pady=2)
        tk.Entry(parent, textvariable=var, width=12).grid(row=row, column=1, sticky="w",
                                                          padx=(4, 0), pady=2)

    def write(self, text):
        self.log.configure(state="normal")
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    # ---------- лог: копирование и сохранение ----------
    def log_text(self):
        """Весь текст лога как строка (без лишних пустых строк в конце)."""
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
        """Кладёт весь лог в буфер обмена.

        Нужно, чтобы отдать результат текстом, а не скриншотом.
        """
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
        self.write(f"  лог скопирован в буфер ({len(text)} символов, "
                   f"{text.count(chr(10)) + 1} строк)")

    def do_save_log(self):
        """Сохраняет лог в .txt (UTF-8 с BOM — открывается в Блокноте)."""
        text = self.log_text()
        if not text.strip():
            self.write("  лог пуст — сохранять нечего")
            return
        import time as _time
        default = "kohya_log_" + _time.strftime("%Y%m%d_%H%M%S") + ".txt"
        start = self.var_output.get().strip() or "."
        path = filedialog.asksaveasfilename(
            parent=self.window, title="Сохранить лог",
            initialfile=default, initialdir=start,
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
        state = tk.DISABLED if on else tk.NORMAL
        for b in (self.btn_check, self.btn_cuda, self.btn_cfg, self.btn_train,
                  self.btn_close):
            b.config(state=state)
        self.btn_stop.config(state=tk.NORMAL if on else tk.DISABLED)
        if on:
            self.progress.start(12)
        else:
            self.progress.stop()

    # ---------- расчёты ----------
    def count_frames(self):
        """Сколько png в папках персонажей (без train/)."""
        root = self.var_dataset.get().strip()
        if not os.path.isdir(root):
            return 0
        total = 0
        for d in os.listdir(root):
            fdir = os.path.join(root, d)
            if os.path.isdir(fdir) and d != "train":
                total += sum(1 for f in os.listdir(fdir) if f.lower().endswith(".png"))
        return total

    def update_steps(self):
        """Показывает, сколько шагов получится, и предупреждает о крайностях."""
        try:
            epochs = int(self.var_epochs.get())
            repeats = int(self.var_repeats.get())
            batch = int(self.var_batch.get())
        except ValueError:
            self.lbl_steps.config(text="шаги: проверьте числа", fg="#aa0000")
            return

        frames = self.count_frames()
        if frames == 0:
            self.lbl_steps.config(text="шаги: кадров не найдено", fg="#aa0000")
            return

        steps = lt.total_steps(frames, repeats, epochs, batch)
        if steps < 300:
            note, color = f"{steps} шагов — маловато, персонаж может не выучить", "#aa0000"
        elif steps > 2000:
            note, color = f"{steps} шагов — много, риск заучить картинки", "#aa6600"
        else:
            note, color = f"{steps} шагов — норма", "#005500"
        self.lbl_steps.config(text=f"{frames} кадров → {note}", fg=color)

    def collect_params(self):
        """Собирает конфиг из полей. Бросает ValueError с понятным текстом."""
        try:
            params = {k: v for k, v in lt.PRESET_3050.items() if k != "название"}
            params["resolution"] = self.var_res.get().strip()
            params["network_dim"] = int(self.var_dim.get())
            params["network_alpha"] = int(self.var_alpha.get())
            params["max_train_epochs"] = int(self.var_epochs.get())
            params["train_batch_size"] = int(self.var_batch.get())
            params["learning_rate"] = float(self.var_lr.get())
        except ValueError as e:
            raise ValueError(f"проверьте числа в параметрах обучения ({e})") from e

        # kohya запускается из своей папки (sd-scripts), поэтому ей нужны
        # АБСОЛЮТНЫЕ пути: относительный 'dataset\\train' она ищет внутри
        # sd-scripts и находит пусто. Разворачиваем в абсолютные заранее.
        cfg = lt.build_config(
            train_data_dir=os.path.abspath(
                os.path.join(self.var_dataset.get().strip(), "train")),
            output_dir=os.path.abspath(self.var_output.get().strip()),
            base_model=self.var_model.get().strip(),
            output_name=self.var_name.get().strip() or "lora",
            params=params,
        )
        return cfg, params

    # ---------- действия ----------
    def do_check(self):
        self.write("\n— проверка готовности —")
        lines = lt.check_ready(
            self.var_dataset.get().strip(),
            self.var_model.get().strip(),
            self.var_kohya.get().strip(),
            self.var_output.get().strip())
        for l in lines:
            self.write("  " + l)
        bad = sum(1 for l in lines if l.startswith("НЕТ"))
        self.write("ИТОГ: " + ("можно начинать" if bad == 0
                               else f"не хватает {bad} пункт(ов), см. НЕТ выше"))

    def do_cuda(self):
        """Отдельно: спрашивает torch, видит ли он видеокарту."""
        self.write("\n— проверка CUDA (несколько секунд) —")
        k = lt.find_kohya(self.var_kohya.get().strip())
        if not k["ok"]:
            self.write("  НЕТ: сначала укажите папку kohya_ss — " + k["msg"])
            return

        def job():
            ok, info = lt.cuda_check(k["python"])
            self.write(("  ОК: " if ok else "  НЕТ: ") + info)
            if not ok:
                self.write("  Без CUDA обучение пойдёт на процессоре — это очень долго.")

        self._in_thread(job)

    def do_save_config(self):
        self.write("\n— сохранение конфига —")
        try:
            cfg, params = self.collect_params()
        except ValueError as e:
            self.write("  ОШИБКА: " + str(e))
            messagebox.showerror("Параметры", str(e), parent=self.window)
            return

        path = os.path.join(self.var_output.get().strip() or ".", "train_config.toml")
        lt.write_config(cfg, path)
        self.write(f"  записано: {os.path.abspath(path)}")
        self.write("  этот файл можно открыть в GUI kohya как конфиг.")

    def do_train(self):
        try:
            cfg, params = self.collect_params()
        except ValueError as e:
            self.write("  ОШИБКА: " + str(e))
            messagebox.showerror("Параметры", str(e), parent=self.window)
            return

        k = lt.find_kohya(self.var_kohya.get().strip())
        if not k["ok"]:
            self.write("\nНЕ ЗАПУЩЕНО: " + k["msg"])
            messagebox.showwarning("kohya не найдена", k["msg"], parent=self.window)
            return
        if not cfg["pretrained_model_name_or_path"] or \
                not os.path.isfile(cfg["pretrained_model_name_or_path"]):
            self.write("\nНЕ ЗАПУЩЕНО: не указана базовая модель (.safetensors)")
            return

        self.write("\n— подготовка структуры train/ для kohya —")
        try:
            repeats = int(self.var_repeats.get())
        except ValueError:
            repeats = 1
        root, total, msgs = lt.prepare_train_dir(
            os.path.abspath(self.var_dataset.get().strip()), repeats)
        for m in msgs:
            self.write("  " + m)
        if root is None:
            self.write("НЕ ЗАПУЩЕНО: структура не подготовлена")
            return
        cfg["train_data_dir"] = root

        cfg_path = os.path.join(self.var_output.get().strip() or ".", "train_config.toml")
        lt.write_config(cfg, cfg_path)

        cmd = lt.train_command(k["python"], k["script"], os.path.abspath(cfg_path))
        self.write("\n— запуск —")
        self.write("  " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
        self.write("")

        self.stop_flag = False
        self._busy(True)

        def job():
            code = lt.run_training(
                cmd, cwd=os.path.dirname(k["script"]),
                on_line=lambda line: self.write("  " + line),
                should_stop=lambda: self.stop_flag)
            if code == 0:
                # код 0 не гарантирует, что было обучение: при пустом
                # датасете kohya тоже выходит с 0. Проверяем файл LoRA.
                lora = self._find_lora(cfg["output_dir"], cfg["output_name"])
                if lora:
                    self.write("\nГОТОВО: обучение завершилось успешно.")
                    self.write(f"  файл LoRA: {lora}")
                else:
                    self.write("\nНЕ ЗАПУЩЕНО: файл LoRA не создан — kohya "
                               "не нашла кадров (см. строки 'No data found' "
                               "или '0 train images' выше).")
            elif code == -1:
                self.write("\nОСТАНОВЛЕНО пользователем.")
            else:
                self.write(f"\nЗАВЕРШИЛОСЬ С ОШИБКОЙ (код {code}). Смотрите строки выше.")

        self._in_thread(job)

    def do_stop(self):
        if self.worker and self.worker.is_alive():
            self.stop_flag = True
            self.write("  ...останавливаю после текущей строки лога")

    def _find_lora(self, output_dir, output_name):
        """Ищет свежий файл LoRA в папке результата.

        kohya пишет либо '<имя>.safetensors', либо '<имя>-last.safetensors'
        (при save_model_as=safetensors). Возвращает путь к самому
        свежему из них или None, если ничего нет.
        """
        try:
            cands = []
            for f in os.listdir(output_dir):
                if not f.lower().endswith(".safetensors"):
                    continue
                if f.lower().startswith(output_name.lower()):
                    full = os.path.join(output_dir, f)
                    cands.append((os.path.getmtime(full), full))
            if not cands:
                return None
            return max(cands)[1]
        except OSError:
            return None

    def _in_thread(self, func):
        self._busy(True)

        def wrapper():
            try:
                func()
            except Exception as e:                      # noqa: BLE001
                self.write(f"ОШИБКА: {e}")
            finally:
                self._busy(False)

        self.worker = threading.Thread(target=wrapper, daemon=True)
        self.worker.start()

    def close(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(
                "Идёт работа",
                "Сначала нажмите «Остановить» и дождитесь завершения.",
                parent=self.window)
            return
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()