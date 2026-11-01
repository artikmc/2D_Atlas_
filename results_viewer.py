import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
from io import BytesIO
import csv
from database import create_connection, get_all_frames, update_frame_class, delete_frame, get_all_classes
from class_selector import ClassSelector
from animation_viewer import AnimationViewer

# Маркеры выбора в панели персонажей: id персонажа — целое число,
# поэтому «все» и «безымянные кадры» нельзя обозначать через None.
CHAR_ALL = "__all__"
CHAR_NONE = "__none__"


class ResultsViewer:
    def __init__(self, parent):
        """Окно результатов: панель персонажей слева, таблица персонаж × класс справа."""
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("Результаты")
        self.window.geometry("1200x700")

        # --- строка фильтра и кнопок ---
        filter_frame = tk.Frame(self.window)
        filter_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(filter_frame, text="Поиск:").pack(side=tk.LEFT, padx=(5, 2), pady=5)

        self.filter_entry = tk.Entry(filter_frame)
        self.filter_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        self.filter_entry.bind("<Return>", lambda e: self.apply_filter())

        self.btn_filter = tk.Button(filter_frame, text="Фильтровать", command=self.apply_filter)
        self.btn_filter.pack(side=tk.LEFT, padx=5, pady=5)

        self.btn_export = tk.Button(filter_frame, text="Экспорт в CSV", command=self.export_to_csv)
        self.btn_export.pack(side=tk.LEFT, padx=5, pady=5)

        self.btn_refresh = tk.Button(filter_frame, text="Обновить", command=self.load_data)
        self.btn_refresh.pack(side=tk.LEFT, padx=5, pady=5)

        # --- основная область: слева персонажи, справа таблица ---
        body = tk.Frame(self.window)
        body.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # ======== ПАНЕЛЬ ПЕРСОНАЖЕЙ ========
        char_panel = tk.Frame(body, width=230)
        char_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        char_panel.pack_propagate(False)   # держим ширину, несмотря на содержимое

        tk.Label(char_panel, text="Персонажи", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")

        list_wrap = tk.Frame(char_panel)
        list_wrap.pack(fill=tk.BOTH, expand=True, pady=3)

        self.char_listbox = tk.Listbox(list_wrap, exportselection=False,
                                       activestyle="dotbox", height=12)
        char_scroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL,
                                    command=self.char_listbox.yview)
        self.char_listbox.configure(yscrollcommand=char_scroll.set)
        self.char_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        char_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.char_listbox.bind("<<ListboxSelect>>", self.on_character_select)
        self.char_listbox.bind("<Double-1>", lambda e: self.rename_character())

        char_btns = tk.Frame(char_panel)
        char_btns.pack(fill=tk.X, pady=(4, 0))

        self.btn_rename_char = tk.Button(char_btns, text="Переименовать",
                                         command=self.rename_character)
        self.btn_rename_char.pack(fill=tk.X, pady=1)

        self.btn_delete_char = tk.Button(char_btns, text="Удалить персонажа",
                                         command=self.delete_selected_character)
        self.btn_delete_char.pack(fill=tk.X, pady=1)

        # ======== ТАБЛИЦА ========
        table_wrap = tk.Frame(body)
        table_wrap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(table_wrap, bg="white")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.v_scroll = ttk.Scrollbar(table_wrap, orient=tk.VERTICAL, command=self.canvas.yview)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll = ttk.Scrollbar(table_wrap, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.canvas.bind("<Configure>", self.on_canvas_configure)

        self.table_frame = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window((0, 0), window=self.table_frame, anchor=tk.NW)

        # --- статусная строка ---
        self.status_label = tk.Label(self.window, text="", anchor="w", fg="#555555")
        self.status_label.pack(fill=tk.X, padx=8, pady=(0, 4))

        # состояние
        self.images = {}
        self.row_main_ids = []          # main_frame_id по индексу строки таблицы
        self.row_character_ids = []     # character_id по индексу строки таблицы
        self.char_entries = []          # [(character_id|None, подпись)] для listbox
        self.selected_character_id = CHAR_ALL
        self._filter_text = None

        self.load_data()

    def on_canvas_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # ================= ДАННЫЕ =================
    def _fetch_groups(self, conn, filter_text=None, character_filter=None):
        """Готовит строки таблицы одним проходом по базе.

        Возвращает (groups, classes, char_stats):
          groups      — [(main_frame_id, character_id, image_bytes, {класс: [кадры]})]
          classes     — все классы (для колонок), 'основной кадр' исключён
          char_stats  — {character_id|None: {"name":…, "main":N, "frames":N}}
        """
        cur = conn.cursor()
        # Старая база (до Части 2) может не иметь ни колонки character_id, ни таблицы
        # characters. Тогда персонажей нет, а таблица строится как раньше.
        frame_cols = {r[1] for r in cur.execute("PRAGMA table_info(frames)")}
        has_char_col = "character_id" in frame_cols
        has_char_table = bool(cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='characters'").fetchone())

        if has_char_col:
            rows = cur.execute(
                "SELECT id, class_name, frame_data, main_frame_id, character_id "
                "FROM frames").fetchall()
        else:
            rows = [(fid, cls, data, mfid, None) for fid, cls, data, mfid in cur.execute(
                "SELECT id, class_name, frame_data, main_frame_id FROM frames").fetchall()]

        names = (dict(cur.execute("SELECT id, name FROM characters").fetchall())
                 if has_char_table else {})

        mains = {}          # main_id -> {"image":…, "character_id":…, "classes":{}}
        classes_all = set()
        char_stats = {}

        for fid, cls, data, mfid, chid in rows:
            if cls == "основной кадр":
                mains[fid] = {"image": data, "character_id": chid, "classes": {}}
                st = char_stats.setdefault(chid, {"name": names.get(chid), "main": 0, "frames": 0})
                st["main"] += 1
            else:
                classes_all.add(cls)

        for fid, cls, data, mfid, chid in rows:
            if cls == "основной кадр":
                continue
            if mfid in mains:
                mains[mfid]["classes"].setdefault(cls, []).append(data)
                st = char_stats.setdefault(mains[mfid]["character_id"],
                                           {"name": names.get(mains[mfid]["character_id"]),
                                            "main": 0, "frames": 0})
                st["frames"] += 1

        # персонажи без единого кадра — тоже показываем (их и надо чистить)
        for cid, cname in names.items():
            char_stats.setdefault(cid, {"name": cname, "main": 0, "frames": 0})

        groups = []
        for mid, data in mains.items():
            groups.append((mid, data["character_id"], data["image"], data["classes"]))

        # фильтр по тексту: имя персонажа или название класса
        if filter_text:
            needle = filter_text.lower()
            kept = []
            for mid, chid, img, cls_map in groups:
                cname = (names.get(chid) or "").lower()
                if needle in cname or any(needle in c.lower() for c in cls_map):
                    kept.append((mid, chid, img, cls_map))
            groups = kept

        # фильтр по выбранному персонажу
        if character_filter == CHAR_NONE:
            groups = [g for g in groups if g[1] is None]
        elif character_filter not in (None, CHAR_ALL):
            groups = [g for g in groups if g[1] == character_filter]

        # сортировка: по имени персонажа, затем по id основного кадра
        groups.sort(key=lambda g: ((names.get(g[1]) or "\uffff"), g[0]))
        return groups, sorted(classes_all), char_stats

    def _reload_character_list(self, char_stats):
        """Заполняет список персонажей: '— все —', затем каждый с количеством кадров."""
        self.char_listbox.delete(0, tk.END)
        self.char_entries = []

        total_main = sum(v["main"] for v in char_stats.values())
        total_frames = sum(v["frames"] for v in char_stats.values())
        self.char_listbox.insert(tk.END, f"— все персонажи ({total_main})")
        self.char_entries.append((CHAR_ALL, "— все персонажи"))

        # сначала те, у кого есть кадры, потом пустые заготовки
        ordered = sorted(char_stats.items(),
                         key=lambda kv: (0 if kv[1]["main"] else 1,
                                         (kv[1]["name"] or "").lower()))
        for cid, st in ordered:
            if cid is None:
                # кадры без персонажа (например, старая база)
                label = f"(без персонажа) — {st['main']} осн., {st['frames']} кадр."
                self.char_listbox.insert(tk.END, label)
                self.char_entries.append((CHAR_NONE, "(без персонажа)"))
                continue
            name = st["name"] or f"персонаж #{cid}"
            if st["main"]:
                label = f"{name} — {st['main']} осн., {st['frames']} кадр."
            else:
                label = f"{name} — пусто"
            self.char_listbox.insert(tk.END, label)
            self.char_entries.append((cid, name))

        # восстановить выбор
        idx = 0
        for i, (cid, _) in enumerate(self.char_entries):
            if cid == self.selected_character_id:
                idx = i
                break
        else:
            self.selected_character_id = CHAR_ALL
            idx = 0
        self.char_listbox.selection_clear(0, tk.END)
        self.char_listbox.selection_set(idx)
        self.char_listbox.see(idx)

        empty = sum(1 for st in char_stats.values() if not st["main"])
        self.status_label.config(
            text=f"Персонажей: {len(char_stats)} (с кадрами: {len(char_stats) - empty}, "
                 f"пустых: {empty})   |   Кадров: {total_main + total_frames}")

    def load_data(self, filter_text=None):
        """Загружает данные и заполняет таблицу. Ячейка класса — прокрутка кадров (◀ ▶)."""
        if filter_text is not None:
            self._filter_text = filter_text
        conn = create_connection()
        if conn is None:
            return
        try:
            groups, classes, char_stats = self._fetch_groups(
                conn, self._filter_text, self.selected_character_id)

            for widget in self.table_frame.winfo_children():
                widget.destroy()
            self.images = {}
            self.row_main_ids = []
            self.row_character_ids = []

            self._reload_character_list(char_stats)

            # ----- заголовок -----
            headers = ["№", "Персонаж", "Основной кадр"] + classes
            for col_idx, column in enumerate(headers):
                is_name = (column == "Персонаж")
                label = tk.Label(self.table_frame, text=column, borderwidth=1, relief=tk.SOLID,
                                 width=18 if is_name else (5 if column == "№" else 13),
                                 height=2,
                                 font=("TkDefaultFont", 9, "bold") if is_name else None)
                label.grid(row=0, column=col_idx, sticky="nsew")

            if not groups:
                tk.Label(self.table_frame, text="Нет строк под текущий фильтр",
                         fg="gray").grid(row=1, column=0, columnspan=len(headers), pady=10,
                                         sticky="w")
                return

            # ----- строки -----
            for row_idx, (main_frame_id, character_id, main_data, cls_map) in enumerate(groups):
                self.row_main_ids.append(main_frame_id)
                self.row_character_ids.append(character_id)
                self._make_number_cell(row_idx, main_frame_id)
                self._make_name_cell(row_idx, character_id, char_stats)
                self._make_main_cell(row_idx, main_frame_id, main_data)
                for col_idx, cls in enumerate(classes):
                    self._make_class_cell(row_idx, col_idx, main_frame_id, cls,
                                          cls_map.get(cls, []))
        finally:
            conn.close()

    # ---------- ячейки ----------
    def _bind_row_events(self, widget, row_idx):
        """Явно привязывает номер строки через замыкание (не через grid_info)."""
        widget.bind("<Button-3>", lambda e, r=row_idx: self.show_context_menu(e, r))
        widget.bind("<Double-1>", lambda e, r=row_idx: self.on_double_click(e, r))

    def _make_number_cell(self, row_idx, main_frame_id):
        label = tk.Label(self.table_frame, text=str(row_idx + 1), borderwidth=1,
                         relief=tk.SOLID, width=5, height=2)
        label.grid(row=row_idx + 1, column=0, sticky="nsew")
        self._bind_row_events(label, row_idx)

    def _make_name_cell(self, row_idx, character_id, char_stats):
        """Имя персонажа строки. Пустая заготовка показывается явно."""
        name = char_stats.get(character_id, {}).get("name")
        text = name if name else "(без имени)"
        fg = "#000000" if name else "#999999"
        label = tk.Label(self.table_frame, text=text, borderwidth=1, relief=tk.SOLID,
                         width=18, height=2, anchor="w", padx=4, fg=fg)
        label.grid(row=row_idx + 1, column=1, sticky="nsew")
        self._bind_row_events(label, row_idx)

    def _make_main_cell(self, row_idx, main_frame_id, main_frame_data):
        cell = tk.Frame(self.table_frame, borderwidth=1, relief=tk.SOLID)
        cell.grid(row=row_idx + 1, column=2, sticky="nsew")
        lbl = None
        try:
            img = Image.open(BytesIO(main_frame_data))
            img.thumbnail((50, 50))
            photo = ImageTk.PhotoImage(img)
            self.images[f"main_{main_frame_id}"] = photo
            lbl = tk.Label(cell, image=photo)
            lbl.image = photo
            lbl.pack()
        except Exception as e:
            lbl = tk.Label(cell, text="ошибка")
            lbl.pack()
            print(f"Ошибка основного кадра {main_frame_id}: {e}")
        self._bind_row_events(cell, row_idx)
        if lbl is not None:
            self._bind_row_events(lbl, row_idx)

    def _make_class_cell(self, row_idx, col_idx, main_frame_id, cls, frames_list):
        """Ячейка класса: один кадр виден, ◀ ▶ листают, счётчик 'k/n'. Колонка не растягивается."""
        cell = tk.Frame(self.table_frame, borderwidth=1, relief=tk.SOLID)
        cell.grid(row=row_idx + 1, column=col_idx + 3, sticky="nsew")

        if not frames_list:
            tk.Label(cell, text="", width=12, height=2).pack()
            self._bind_row_events(cell, row_idx)
            return

        # миниатюры всех кадров класса
        thumbs = []
        for fi, fdata in enumerate(frames_list):
            try:
                img = Image.open(BytesIO(fdata))
                img.thumbnail((40, 40))
                photo = ImageTk.PhotoImage(img)
                self.images[f"class_{main_frame_id}_{cls}_{fi}"] = photo
                thumbs.append(photo)
            except Exception as e:
                print(f"Ошибка кадра {cls}#{fi}: {e}")
        if not thumbs:
            tk.Label(cell, text="", width=12, height=2).pack()
            self._bind_row_events(cell, row_idx)
            return

        state = {"i": 0}
        nav = tk.Frame(cell)
        nav.pack()
        view = tk.Label(nav, image=thumbs[0])
        counter = tk.Label(nav, text=f"1/{len(thumbs)}", fg="gray")
        if len(thumbs) == 1:
            view.pack(side=tk.LEFT)
        else:
            btn_prev = tk.Button(nav, text="◀", width=2,
                                 command=lambda: self._step(state, thumbs, view, counter, -1))
            btn_next = tk.Button(nav, text="▶", width=2,
                                 command=lambda: self._step(state, thumbs, view, counter, +1))
            btn_prev.pack(side=tk.LEFT)
            view.pack(side=tk.LEFT)
            btn_next.pack(side=tk.LEFT)
            counter.pack(side=tk.LEFT, padx=2)

        # правый клик и двойной клик по любой части ячейки = строка row_idx
        self._bind_row_events(cell, row_idx)
        for w in (nav, view, counter):
            self._bind_row_events(w, row_idx)
        # запоминаем кадры класса для двойного клика (открыть просмотр этого класса)
        cell._class_frames = frames_list
        cell._class_name = cls
        view._class_frames = frames_list
        view._class_name = cls

    def _step(self, state, thumbs, view, counter, delta):
        n = len(thumbs)
        state["i"] = (state["i"] + delta) % n
        view.configure(image=thumbs[state["i"]])
        counter.configure(text=f"{state['i'] + 1}/{n}")

    # ---------- выбор персонажа ----------
    def on_character_select(self, event=None):
        sel = self.char_listbox.curselection()
        if not sel:
            return
        cid, _ = self.char_entries[sel[0]]
        self.selected_character_id = cid
        self.load_data()

    def _current_character(self):
        """(character_id, имя) выбранного в списке персонажа или (None, None)."""
        sel = self.char_listbox.curselection()
        if not sel:
            return None, None
        cid, name = self.char_entries[sel[0]]
        if cid in (CHAR_ALL, CHAR_NONE):
            return None, None
        return cid, name

    # ---------- фильтры/экспорт ----------
    def apply_filter(self):
        self.load_data(self.filter_entry.get())

    def export_to_csv(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not file_path:
            return
        try:
            conn = create_connection()
            if conn is None:
                return
            with open(file_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                classes = get_all_classes(conn)
                writer.writerow(["ID основного кадра", "Персонаж"] + classes)
                cur = conn.cursor()
                has_char_table = bool(cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='characters'"
                ).fetchone())
                has_char_col = "character_id" in {r[1] for r in cur.execute("PRAGMA table_info(frames)")}
                names = (dict(cur.execute("SELECT id, name FROM characters").fetchall())
                         if has_char_table else {})
                col = "character_id" if has_char_col else "NULL"
                mains = cur.execute(
                    f"SELECT id, {col} FROM frames WHERE class_name = 'основной кадр' "
                    f"ORDER BY id").fetchall()
                for mid, chid in mains:
                    counts = []
                    for cls in classes:
                        c = cur.execute(
                            "SELECT COUNT(*) FROM frames WHERE main_frame_id=? AND class_name=?",
                            (mid, cls)).fetchone()[0]
                        counts.append(c)
                    writer.writerow([mid, names.get(chid, "")] + counts)
            conn.close()
            messagebox.showinfo("Успех", f"Данные экспортированы в {file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать данные: {e}")

    # ---------- контекстное меню ----------
    def show_context_menu(self, event, row):
        self.selected_row = row
        self._last_event_widget = event.widget
        context_menu = tk.Menu(self.window, tearoff=0)
        context_menu.add_command(label="Редактировать строку", command=self.edit_frame)
        context_menu.add_command(label="Удалить строку (с кадрами)", command=self.delete_frame)

        chid = self.row_character_ids[row] if 0 <= row < len(self.row_character_ids) else None
        if chid is not None:
            context_menu.add_separator()
            context_menu.add_command(
                label="Удалить персонажа со всеми кадрами",
                command=lambda: self.delete_character(chid))
        context_menu.post(event.x_root, event.y_root)

    def edit_frame(self):
        """Двойной клик/ПКМ: открыть AnimationViewer. Если клик был по ячейке класса — показать её кадры,
        иначе — основной кадр строки."""
        row = getattr(self, "selected_row", None)
        if row is None:
            return
        widget = getattr(self, "_last_event_widget", None)
        frames_list = getattr(widget, "_class_frames", None) if widget else None
        class_name = getattr(widget, "_class_name", None) if widget else None

        main_frame_id = self.get_frame_id_by_row(row)
        if main_frame_id is None:
            return
        conn = create_connection()
        if conn is None:
            return
        try:
            cur = conn.cursor()
            if frames_list:
                # склеиваем кадры класса в одну полосу — AnimationViewer сам их разрежет детекцией
                strip = self._stitch(frames_list)
                character_id = self.get_character_id_by_row(row)
                AnimationViewer(self.window, strip, class_name, main_frame_id, character_id)
            else:
                cur.execute("SELECT frame_data, class_name, character_id FROM frames WHERE id=?",
                            (main_frame_id,))
                row_data = cur.fetchone()
                if row_data is None:
                    return
                frame_data, cname, character_id = row_data
                image = Image.open(BytesIO(frame_data))
                AnimationViewer(self.window, image, cname, main_frame_id, character_id)
        finally:
            conn.close()

    def _stitch(self, frames_list, gap=4):
        frames = [Image.open(BytesIO(d)).convert("RGBA") for d in frames_list]
        total_w = sum(f.width for f in frames) + gap * (len(frames) - 1)
        max_h = max(f.height for f in frames)
        strip = Image.new("RGBA", (total_w, max_h), (0, 0, 0, 0))
        x = 0
        for f in frames:
            strip.paste(f, (x, 0), f)
            x += f.width + gap
        return strip

    def delete_frame(self):
        """Удаляет строку: основной кадр и все привязанные к нему кадры классов."""
        row = getattr(self, "selected_row", None)
        if row is None:
            return
        main_frame_id = self.get_frame_id_by_row(row)
        if main_frame_id is None:
            return
        chid = self.get_character_id_by_row(row)
        if chid is not None:
            extra = ("\n\nПерсонаж останется в списке как пустой — "
                     "удалить его целиком можно кнопкой «Удалить персонажа».")
        else:
            extra = ""
        if not messagebox.askyesno("Подтверждение",
                                   "Удалить строку вместе со всеми её кадрами классов?" + extra):
            return
        conn = create_connection()
        if conn is None:
            return
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM frames WHERE id = ? OR main_frame_id = ?",
                        (main_frame_id, main_frame_id))
            conn.commit()
            messagebox.showinfo("Успех", "Строка удалена")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить строку: {e}")
        finally:
            conn.close()
        self.load_data()

    # ---------- персонажи ----------
    def rename_character(self):
        """Переименование выбранного персонажа (двойной клик по списку или кнопка)."""
        cid, old_name = self._current_character()
        if cid is None:
            messagebox.showinfo("Персонаж не выбран",
                                "Выберите персонажа в списке слева (не «— все персонажи —»).")
            return
        new_name = simpledialog.askstring("Переименовать персонажа",
                                          f"Новое имя для «{old_name}»:",
                                          initialvalue=old_name or "",
                                          parent=self.window)
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            messagebox.showwarning("Пустое имя", "Имя не может быть пустым.")
            return
        if new_name == old_name:
            return
        conn = create_connection()
        if conn is None:
            return
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM characters WHERE name = ? AND id != ?", (new_name, cid))
            if cur.fetchone():
                messagebox.showerror("Имя занято", f"Персонаж «{new_name}» уже существует.")
                return
            cur.execute("UPDATE characters SET name = ? WHERE id = ?", (new_name, cid))
            conn.commit()
            messagebox.showinfo("Готово", f"Персонаж переименован в «{new_name}».")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось переименовать: {e}")
        finally:
            conn.close()
        self.load_data()

    def delete_selected_character(self):
        """Кнопка «Удалить персонажа» — по выбору в списке слева."""
        cid, name = self._current_character()
        if cid is None:
            messagebox.showinfo("Персонаж не выбран",
                                "Выберите персонажа в списке слева (не «— все персонажи —»).")
            return
        self.delete_character(cid, name)

    def delete_character(self, character_id, name=None):
        """Удаляет персонажа и все его кадры. Для пустой заготовки — просто запись."""
        conn = create_connection()
        if conn is None:
            return
        try:
            cur = conn.cursor()
            if name is None:
                r = cur.execute("SELECT name FROM characters WHERE id = ?",
                                (character_id,)).fetchone()
                name = r[0] if r else f"#{character_id}"

            main_ids = [r[0] for r in cur.execute(
                "SELECT id FROM frames WHERE class_name = 'основной кадр' AND character_id = ?",
                (character_id,)).fetchall()]
            n_frames = cur.execute("SELECT COUNT(*) FROM frames WHERE character_id = ?",
                                   (character_id,)).fetchone()[0]

            if n_frames:
                question = (f"Удалить персонажа «{name}»?\n\n"
                            f"Будут удалены все его кадры: {n_frames} "
                            f"(включая {len(main_ids)} основных).\n"
                            f"Действие необратимо.")
            else:
                question = f"Удалить пустую заготовку «{name}»?"

            if not messagebox.askyesno("Подтверждение", question):
                return

            # кадры персонажа + всё, что ссылается на его основные кадры
            if main_ids:
                placeholders = ",".join("?" * len(main_ids))
                cur.execute(
                    f"DELETE FROM frames WHERE character_id = ? OR main_frame_id IN ({placeholders})",
                    (character_id, *main_ids))
            else:
                cur.execute("DELETE FROM frames WHERE character_id = ?", (character_id,))
            cur.execute("DELETE FROM characters WHERE id = ?", (character_id,))
            conn.commit()
            messagebox.showinfo("Готово", f"Персонаж «{name}» удалён.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить персонажа: {e}")
        finally:
            conn.close()
        if self.selected_character_id == character_id:
            self.selected_character_id = CHAR_ALL
        self.load_data()

    def on_double_click(self, event, row):
        self.selected_row = row
        self._last_event_widget = event.widget
        self.edit_frame()

    def get_frame_id_by_row(self, row):
        """ID основного кадра по номеру строки — из кэша текущей отрисовки.

        Раньше здесь заново шёл SELECT по всем основным кадрам, из-за чего при
        активном фильтре номер строки указывал на чужой кадр.
        """
        if 0 <= row < len(self.row_main_ids):
            return self.row_main_ids[row]
        return None

    def get_character_id_by_row(self, row):
        """ID персонажа по номеру строки (из кэша текущей отрисовки)."""
        if 0 <= row < len(self.row_character_ids):
            return self.row_character_ids[row]
        return None

    def get_main_frame_id_for_class(self, conn, frame_id):
        """ID основного кадра для кадра класса (связь прямо из frames)."""
        cursor = conn.cursor()
        cursor.execute("SELECT main_frame_id FROM frames WHERE id = ?", (frame_id,))
        result = cursor.fetchone()
        return result[0] if result else None