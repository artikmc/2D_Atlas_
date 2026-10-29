import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from io import BytesIO
import csv
from database import create_connection, get_all_frames, update_frame_class, delete_frame, get_all_classes
from class_selector import ClassSelector
from animation_viewer import AnimationViewer


class ResultsViewer:
    def __init__(self, parent):
        """Окно результатов: таблица персонаж(основной кадр) × класс, с прокруткой кадров в ячейке."""
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("Результаты")

        filter_frame = tk.Frame(self.window)
        filter_frame.pack(fill=tk.X, padx=5, pady=5)

        self.filter_entry = tk.Entry(filter_frame)
        self.filter_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)

        self.btn_filter = tk.Button(filter_frame, text="Фильтровать", command=self.apply_filter)
        self.btn_filter.pack(side=tk.LEFT, padx=5, pady=5)

        self.btn_export = tk.Button(filter_frame, text="Экспорт в CSV", command=self.export_to_csv)
        self.btn_export.pack(side=tk.LEFT, padx=5, pady=5)

        self.btn_refresh = tk.Button(filter_frame, text="Обновить", command=self.load_data)
        self.btn_refresh.pack(side=tk.LEFT, padx=5, pady=5)

        self.canvas = tk.Canvas(self.window, bg="white")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.v_scroll = ttk.Scrollbar(self.window, orient=tk.VERTICAL, command=self.canvas.yview)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll = ttk.Scrollbar(self.window, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.canvas.bind("<Configure>", self.on_canvas_configure)

        self.table_frame = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window((0, 0), window=self.table_frame, anchor=tk.NW)

        self.images = {}
        self.load_data()

    def on_canvas_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def load_data(self, filter_text=None):
        """Загружает данные и заполняет таблицу. Ячейка класса — прокрутка кадров (◀ ▶)."""
        conn = create_connection()
        if conn is None:
            return
        try:
            classes = get_all_classes(conn)
            frames = get_all_frames(conn)

            if filter_text:
                frames = [f for f in frames if filter_text.lower() in f[1].lower()]

            for widget in self.table_frame.winfo_children():
                widget.destroy()
            self.images = {}

            headers = ["№", "Основной кадр"] + classes
            for col_idx, column in enumerate(headers):
                label = tk.Label(self.table_frame, text=column, borderwidth=1, relief=tk.SOLID,
                                 width=15, height=2)
                label.grid(row=0, column=col_idx, sticky="nsew")

            # Группировка: основной кадр -> {класс -> [данные кадров]}
            main_frames = {}
            for frame in frames:
                frame_id, class_name, frame_data = frame
                if class_name == "основной кадр":
                    main_frames[frame_id] = {"main_frame": frame_data, "classes": {}}
                else:
                    main_frame_id = self.get_main_frame_id_for_class(conn, frame_id)
                    if main_frame_id is not None and main_frame_id in main_frames:
                        bucket = main_frames[main_frame_id]["classes"].setdefault(class_name, [])
                        bucket.append(frame_data)

            # Заполнение строк
            for row_idx, (main_frame_id, data) in enumerate(main_frames.items()):
                self._make_number_cell(row_idx, main_frame_id)
                self._make_main_cell(row_idx, main_frame_id, data["main_frame"])
                for col_idx, cls in enumerate(classes):
                    self._make_class_cell(row_idx, col_idx, main_frame_id, cls,
                                          data["classes"].get(cls, []))
        finally:
            conn.close()

    # ---------- ячейки ----------
    def _bind_row_events(self, widget, row_idx):
        """Явно привязывает номер строки через замыкание (не через grid_info)."""
        widget.bind("<Button-3>", lambda e, r=row_idx: self.show_context_menu(e, r))
        widget.bind("<Double-1>", lambda e, r=row_idx: self.on_double_click(e, r))

    def _make_number_cell(self, row_idx, main_frame_id):
        label = tk.Label(self.table_frame, text=str(row_idx + 1), borderwidth=1,
                         relief=tk.SOLID, width=15, height=2)
        label.grid(row=row_idx + 1, column=0, sticky="nsew")
        self._bind_row_events(label, row_idx)

    def _make_main_cell(self, row_idx, main_frame_id, main_frame_data):
        cell = tk.Frame(self.table_frame, borderwidth=1, relief=tk.SOLID)
        cell.grid(row=row_idx + 1, column=1, sticky="nsew")
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
        cell.grid(row=row_idx + 1, column=col_idx + 2, sticky="nsew")

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
                writer.writerow(["ID основного кадра"] + classes)
                cur = conn.cursor()
                mains = cur.execute(
                    "SELECT id FROM frames WHERE class_name = 'основной кадр' ORDER BY id").fetchall()
                for (mid,) in mains:
                    counts = []
                    for cls in classes:
                        c = cur.execute(
                            "SELECT COUNT(*) FROM frames WHERE main_frame_id=? AND class_name=?",
                            (mid, cls)).fetchone()[0]
                        counts.append(c)
                    writer.writerow([mid] + counts)
            conn.close()
            messagebox.showinfo("Успех", f"Данные экспортированы в {file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать данные: {e}")

    # ---------- контекстное меню ----------
    def show_context_menu(self, event, row):
        self.selected_row = row
        context_menu = tk.Menu(self.window, tearoff=0)
        context_menu.add_command(label="Редактировать строку", command=self.edit_frame)
        context_menu.add_command(label="Удалить строку (с кадрами)", command=self.delete_frame)
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
                cur.execute("SELECT character_id FROM frames WHERE id=?", (main_frame_id,))
                r = cur.fetchone()
                character_id = r[0] if r else None
                AnimationViewer(self.window, strip, class_name, main_frame_id, character_id)
            else:
                cur.execute("SELECT frame_data, class_name, character_id FROM frames WHERE id=?",
                            (main_frame_id,))
                frame_data, cname, character_id = cur.fetchone()
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
        if not messagebox.askyesno("Подтверждение",
                                   "Удалить строку вместе со всеми её кадрами классов?"):
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

    def on_double_click(self, event, row):
        self.selected_row = row
        self._last_event_widget = event.widget
        self.edit_frame()

    def get_frame_id_by_row(self, row):
        """ID основного кадра по номеру строки (строки = основные кадры по возрастанию id)."""
        conn = create_connection()
        if conn is None:
            return None
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM frames WHERE class_name = 'основной кадр' ORDER BY id")
            main_ids = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()
        if 0 <= row < len(main_ids):
            return main_ids[row]
        return None

    def get_main_frame_id_for_class(self, conn, frame_id):
        """ID основного кадра для кадра класса (связь прямо из frames)."""
        cursor = conn.cursor()
        cursor.execute("SELECT main_frame_id FROM frames WHERE id = ?", (frame_id,))
        result = cursor.fetchone()
        return result[0] if result else None
