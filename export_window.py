# -*- coding: utf-8 -*-
"""
Окно «Модуль ИИ» — то, что вызывается кнопкой self.btn_ai_module.

Сейчас здесь ОДНО действие: экспорт датасета. Это первое реальное, что делает
модуль. Обучение и генерация появятся позже, в этом же окне.

Запуск экспорта идёт в отдельном потоке: тяжёлая обработка 29 картинок не
должна подвешивать окно. Когда поток закончил — результат выводится в поле.

Окно модальное (grab_set), как EnhanceWindow: пока оно открыто, главное окно
не трогается. Закрываться во время работы нельзя — кнопка «Закрыть» блокируется.
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# импортируем готовый модуль экспорта; он не требует GPU и torch
from dataset_export import export_dataset, DEFAULT_DATASET_ROOT

# verify_dataset появился в новой версии dataset_export.py.
# Если у вас на диске старая версия — окно всё равно должно открыться,
# поэтому подхватываем функцию, если она есть, иначе берём свою простую проверку.
try:
    from dataset_export import verify_dataset
except ImportError:                      # старая версия файла экспорта
    verify_dataset = None


class ExportWindow:
    def __init__(self, parent, db_path="atlas_database.db"):
        """Окно модуля ИИ: экспорт датасета с предпросмотром и логом."""
        self.parent = parent
        self.db_path = db_path
        self.worker = None
        self.queue = queue.Queue()

        self.window = tk.Toplevel(parent)
        self.window.title("Модуль ИИ — датасет")
        self.window.geometry("760x560")
        self.window.transient(parent)
        self.window.grab_set()

        # ---------- сверху: что и куда ----------
        header = tk.Frame(self.window)
        header.pack(fill=tk.X, padx=10, pady=(10, 0))

        tk.Label(header, text="База данных:").grid(row=0, column=0, sticky="w")
        self.lbl_db = tk.Label(header, text=os.path.abspath(self.db_path),
                               fg="#333333", anchor="w")
        self.lbl_db.grid(row=0, column=1, sticky="we", padx=(6, 0))

        tk.Label(header, text="Куда писать:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.out_var = tk.StringVar(value=DEFAULT_DATASET_ROOT)
        self.entry_out = tk.Entry(header, textvariable=self.out_var)
        self.entry_out.grid(row=1, column=1, sticky="we", padx=(6, 4), pady=(4, 0))
        self.btn_browse = tk.Button(header, text="...", width=3, command=self.pick_folder)
        self.btn_browse.grid(row=1, column=2, pady=(4, 0))

        header.columnconfigure(1, weight=1)

        # ---------- кнопки ----------
        btns = tk.Frame(self.window)
        btns.pack(fill=tk.X, padx=10, pady=10)

        self.btn_preview = tk.Button(btns, text="Предпросмотр", command=self.do_preview)
        self.btn_preview.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_run = tk.Button(btns, text="Экспортировать датасет", command=self.do_export)
        self.btn_run.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_check = tk.Button(btns, text="Проверить", command=self.do_check)
        self.btn_check.pack(side=tk.LEFT, padx=(0, 6))

        self.var_code_check = tk.BooleanVar(value=False)
        self.chk_code = tk.Checkbutton(btns, text="Проверять коды тегов",
                                       variable=self.var_code_check)
        self.chk_code.pack(side=tk.LEFT, padx=(4, 0))

        self.progress = ttk.Progressbar(btns, mode="indeterminate", length=120)
        self.progress.pack(side=tk.LEFT, padx=6)

        self.btn_close = tk.Button(btns, text="Закрыть", command=self.close)
        self.btn_close.pack(side=tk.RIGHT)

        # ---------- лог ----------
        log_wrap = tk.Frame(self.window)
        log_wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.log = tk.Text(log_wrap, wrap="word", height=18, bg="white")
        log_scroll = ttk.Scrollbar(log_wrap, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(state="disabled")

        self.write("Модуль ИИ: экспорт датасета для обучения LoRA.")
        self.write("В базе ищутся кадры, сгруппированные по персонажу и классу.")
        self.write("Результат — папка с PNG 512x512 и подписями .txt для kohya_ss.\n")
        self.write("«Предпросмотр» — ничего не пишет на диск, только показывает caption.")
        self.write("«Экспортировать» — пишет папку и сразу проверяет результат.\n")

    # ---------- вспомогательное ----------
    def write(self, text):
        self.log.configure(state="normal")
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def pick_folder(self):
        path = filedialog.askdirectory(parent=self.window,
                                       title="Куда сохранить датасет")
        if path:
            self.out_var.set(path)

    def _busy(self, on):
        """Блокирует кнопки на время работы потока."""
        state = tk.DISABLED if on else tk.NORMAL
        for b in (self.btn_preview, self.btn_run, self.btn_check, self.btn_close,
                  self.btn_browse):
            b.config(state=state)
        if on:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _run_in_thread(self, func):
        """Запускает func в фоне, результат печатает по завершении."""
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

    # ---------- действия ----------
    def do_preview(self):
        self.write("\n— предпросмотр —")

        def job():
            info = export_dataset(self.db_path, dry_run=True)
            self.write(f"Персонажи: {info['characters']}")
            self.write(f"Позы: {info['poses']}")
            self.write(f"Кадров: {info['frames']}")
            self.write("")
            for png, txt, caption in info["files"][:6]:
                self.write(f"{os.path.basename(png)}")
                self.write(f"    {caption}")
            if info["frames"] > 6:
                self.write(f"... и ещё {info['frames'] - 6} кадров")
            self.write("Диск не тронут.")

        self._run_in_thread(job)

    def do_export(self):
        out = self.out_var.get().strip() or DEFAULT_DATASET_ROOT
        self.write(f"\n— экспорт в {os.path.abspath(out)} —")

        def job():
            info = export_dataset(self.db_path, out_root=out, dry_run=False)
            self.write(f"Записано кадров: {info['frames']} "
                       f"(файлов {info['frames'] * 2}: png + txt)")
            self.write(f"Папка: {os.path.abspath(os.path.join(out, info['characters'][0]) if info['characters'] else out)}")
            self.write("")
            self._print_check(out)
            if self.var_code_check.get():
                self._print_tag_codes(out)

        self._run_in_thread(job)

    def do_check(self):
        out = self.out_var.get().strip() or DEFAULT_DATASET_ROOT
        self.write(f"\n— проверка {os.path.abspath(out)} —")

        def job():
            self._print_check(out)
            if self.var_code_check.get():
                self._print_tag_codes(out)

        self._run_in_thread(job)

    def _local_check(self, out):
        """Запасная проверка для старой версии dataset_export.py.

        Смотрит только то, что видно без базы: есть ли папки, у каждого ли png
        есть парный .txt, нет ли пустых caption, все ли кадры 512x512.
        """
        if not os.path.isdir(out):
            return False, [f"папки нет: {os.path.abspath(out)} — сначала запустите экспорт"]

        msgs, ok, total = [], True, 0
        sizes = set()
        for folder in sorted(os.listdir(out)):
            fdir = os.path.join(out, folder)
            if not os.path.isdir(fdir):
                continue
            files = os.listdir(fdir)
            pngs = [f for f in files if f.endswith(".png")]
            if not pngs:
                msgs.append(f"{folder}: нет png")
                ok = False
                continue
            txts = set(f for f in files if f.endswith(".txt"))
            for p in pngs:
                base = p[:-4]
                if base + ".txt" not in txts:
                    msgs.append(f"{folder}/{p}: нет парного .txt")
                    ok = False
                    continue
                tpath = os.path.join(fdir, base + ".txt")
                if not open(tpath, encoding="utf-8").read().strip():
                    msgs.append(f"{folder}/{p}: пустой caption")
                    ok = False
                try:
                    from PIL import Image
                    sizes.add(Image.open(os.path.join(fdir, p)).size)
                except Exception as e:              # noqa: BLE001
                    msgs.append(f"{folder}/{p}: не открывается ({e})")
                    ok = False
                total += 1

        if len(sizes) == 1:
            msgs.append(f"холст: {sizes.pop()} во всех кадрах")
        elif sizes:
            msgs.append(f"ВНИМАНИЕ: разные размеры холста {sorted(sizes)}")
        msgs.append(f"проверено кадров: {total}")
        return ok, msgs

    def _print_check(self, out):
        """Общая часть: прогнать проверку и напечатать."""
        if verify_dataset is not None:
            ok, msgs = verify_dataset(self.db_path, out_root=out)
        else:
            self.write("  (используется упрощённая проверка: "
                       "на диске старая версия dataset_export.py)")
            ok, msgs = self._local_check(out)
        for m in msgs:
            self.write("  " + m)
        self.write("ИТОГ: " + ("всё в порядке" if ok else "есть проблемы"))
        if not ok:
            messagebox.showwarning("Проверка", "Найдены проблемы, см. список в окне.",
                                   parent=self.window)

    def _print_tag_codes(self, out):
        """Печатает коды спорных символов в тегах внешности (цифра/буква).

        Нужен потому, что шрифт редактора и Tk рисуют '1' и 'l' одинаково,
        а модель читает байты файла. Проверяем по коду: 49 = '1', 108 = 'l'.
        """
        # (слово, ожидаемая цифра): '1boy', '1girl' — стандартные теги SD.
        # проверяем именно код символа перед словом, потому что шрифт рисует
        # '1' и 'l' одинаково, а модель читает байты файла.
        suspects = (("boy", 49), ("girl", 49))
        checked = 0
        bad = []
        for folder in sorted(os.listdir(out)):
            fdir = os.path.join(out, folder)
            if not os.path.isdir(fdir):
                continue
            # проверяем каждый txt в папке — иначе одна хорошая подпись
            # закроет глаза на остальные, где может быть опечатка
            for t in sorted(f for f in os.listdir(fdir) if f.endswith(".txt")):
                s = open(os.path.join(fdir, t), encoding="utf-8").read()
                for w, want in suspects:
                    start = 0
                    while True:
                        i = s.find(w, start)
                        if i <= 0:
                            break
                        start = i + len(w)
                        ch = s[i - 1]
                        code = ord(ch)
                        checked += 1
                        if code == want:    # нужная цифра — всё верно
                            continue
                        bad.append(f"{folder}/{t}: перед '{w}' символ {ch!r} "
                                   f"(код {code}, надо {want})")
        if bad:
            for b in bad[:5]:
                self.write("  " + b)
            self.write(f"  ИТОГО подозрительных: {len(bad)}")
        elif checked:
            self.write(f"  коды тегов верны: '1' (=49) во всех проверенных "
                       f"({checked} вхождений)")

    def close(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Идёт работа",
                                "Дождитесь окончания — иначе файлы останутся недописанными.",
                                parent=self.window)
            return
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()