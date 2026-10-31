import tkinter as tk
from tkinter import colorchooser, simpledialog
from PIL import Image, ImageTk, ImageDraw, ImageFont
from language_manager import LanguageManager


class PaintApp(tk.Toplevel):
    """Редактор одного кадра: кисть, ластик, зум, шахматная подложка,
    сетка пикселей и подсветка пикселя под курсором."""

    MIN_CHECKER = 4      # минимальная клетка шахматки в экранных пикселях
    MIN_ZOOM = 1
    MAX_ZOOM = 16
    UNDO_LIMIT = 50      # сколько шагов помнить для отмены

    def __init__(self, master, image=None, zoom=8):
        super().__init__(master)
        self.title(LanguageManager.get_text("paint_title"))

        self.brush_color = "black"
        self.brush_size = 5
        self.last_x, self.last_y = None, None
        self.text_mode = False

        self.eraser_mode = False       # ластик: мазок в прозрачность
        self.pipette_mode = False      # пипетка: клик берёт цвет пикселя
        self.grid_enabled = False      # сетка по пикселям
        self._checker_cache = None     # ((w, h), PIL.Image) — подложка не пересобирается зря
        self._last_pixel = None        # последний пиксель под курсором (для восстановления рамки)

        self._undo_stack = []          # снимки image ДО действия (для «Отменить»)
        self._redo_stack = []          # снимки, отменённые и доступные для «Вернуть»
        self._stroke_snapshot = None   # снимок на старте мазка — один шаг отмены на весь мазок

        if image is not None:
            self.image = image.convert("RGBA")   # редактируем конкретный кадр
            self.zoom = max(self.MIN_ZOOM, int(zoom))
        else:
            self.image = Image.new("RGBA", (800, 600), (255, 255, 255))
            self.zoom = 1

        self.create_widgets()
        self.bind_events()
        self._bind_keys()

        LanguageManager.add_observer(self)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.update_canvas()           # кадр виден сразу, без первого мазка
        self.canvas.focus_set()        # чтобы стрелки и Ctrl+Z работали без лишнего клика

    # ---------------- интерфейс ----------------
    def create_widgets(self):
        """Панель инструментов сверху, статус-строка снизу, холст с прокруткой."""
        control_frame = tk.Frame(self)
        control_frame.pack(side=tk.TOP, fill=tk.X)

        self.btn_color = tk.Button(control_frame, command=self.select_color)
        self.btn_color.pack(side=tk.LEFT)

        # образец текущего цвета: квадратик 22×22 + код hex; клик по квадратику — палитра
        self.color_swatch = tk.Frame(control_frame, width=22, height=22,
                                     bg=self.brush_color, relief=tk.SUNKEN, bd=1,
                                     cursor="hand2")
        self.color_swatch.pack(side=tk.LEFT, padx=(2, 0))
        self.color_swatch.pack_propagate(False)
        self.color_swatch.bind("<Button-1>", lambda e: self.select_color())

        self.color_hex_label = tk.Label(control_frame, text=self.brush_color.upper(),
                                        font=("Consolas", 9), width=9, anchor="w")
        self.color_hex_label.pack(side=tk.LEFT)

        self.brush_size_slider = tk.Scale(control_frame, from_=1, to=30, orient=tk.HORIZONTAL,
                                          length=120)
        self.brush_size_slider.set(self.brush_size)
        self.brush_size_slider.pack(side=tk.LEFT)

        self.btn_eraser = tk.Button(control_frame, text="Ластик", command=self.toggle_eraser)
        self.btn_eraser.pack(side=tk.LEFT, padx=4)
        self._btn_eraser_bg = self.btn_eraser.cget("bg")

        self.btn_grid = tk.Button(control_frame, text="Сетка", command=self.toggle_grid)
        self.btn_grid.pack(side=tk.LEFT, padx=4)
        self._btn_grid_bg = self.btn_grid.cget("bg")

        self.btn_pipette = tk.Button(control_frame, text="Пипетка", command=self.toggle_pipette)
        self.btn_pipette.pack(side=tk.LEFT, padx=4)
        self._btn_pipette_bg = self.btn_pipette.cget("bg")

        self.btn_text = tk.Button(control_frame, command=self.add_text)
        self.btn_text.pack(side=tk.LEFT)

        self.btn_undo = tk.Button(control_frame, text="↶", width=2, command=self.undo,
                                  font=("Arial", 11))
        self.btn_undo.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_redo = tk.Button(control_frame, text="↷", width=2, command=self.redo,
                                  font=("Arial", 11))
        self.btn_redo.pack(side=tk.LEFT)

        self.btn_flip = tk.Button(control_frame, text="↔ Зеркало", command=self.flip_horizontal)
        self.btn_flip.pack(side=tk.LEFT, padx=(8, 0))

        self.zoom_slider = tk.Scale(control_frame, from_=self.MIN_ZOOM, to=self.MAX_ZOOM,
                                    orient=tk.HORIZONTAL, label="Масштаб", length=140,
                                    command=self.set_zoom)
        self.zoom_slider.set(self.zoom)
        self.zoom_slider.pack(side=tk.LEFT, padx=4)

        # статус-строка: координаты пикселя и его цвет
        self.status_var = tk.StringVar(value="")
        self.status_label = tk.Label(self, textvariable=self.status_var, anchor="w",
                                     relief=tk.SUNKEN, font=("Consolas", 9))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # холст в рамке с прокруткой (нужна при большом масштабе)
        canvas_frame = tk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        w = min(self.image.width * self.zoom, 900)
        h = min(self.image.height * self.zoom, 650)
        self.canvas = tk.Canvas(canvas_frame, width=w, height=h,
                                bg="#3a3a3a", highlightthickness=0,
                                cursor="crosshair")
        self.vbar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.hbar = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.config(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.update_texts()

    def bind_events(self):
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up, add="+")
        self.bind("<ButtonRelease-1>", self.on_mouse_up, add="+")   # отпустили мышь вне холста
        self.canvas.bind("<ButtonRelease-1>", self.place_text, add="+")
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Leave>", self.on_mouse_leave)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Alt-Button-1>", self.on_alt_click)   # Alt+клик — быстро взять цвет

    def _bind_keys(self):
        """Горячие клавиши. Стрелки — только на холсте, чтобы не конфликтовать с ползунками."""
        for seq in ("<Control-z>", "<Control-Z>"):
            self.bind(seq, lambda e: self.undo())
            self.canvas.bind(seq, lambda e: self.undo())
        for seq in ("<Control-y>", "<Control-Y>", "<Control-Shift-Z>", "<Control-Shift-z>"):
            self.bind(seq, lambda e: self.redo())
            self.canvas.bind(seq, lambda e: self.redo())
        for key, (dx, dy) in (("Left", (-1, 0)), ("Right", (1, 0)),
                              ("Up", (0, -1)), ("Down", (0, 1))):
            self.canvas.bind(f"<{key}>", lambda e, dx=dx, dy=dy: self.shift_image(dx, dy))
            self.canvas.bind(f"<Shift-{key}>", lambda e, dx=dx, dy=dy: self.shift_image(dx * 10, dy * 10))
        self.canvas.bind("<Button-1>", lambda e: self.canvas.focus_set(), add="+")

    def language_changed(self):
        """Вызывается при смене языка."""
        self.update_texts()

    def update_texts(self):
        """Обновляет все тексты окна по текущему языку."""
        self.title(LanguageManager.get_text("paint_title"))
        self.btn_color.config(text=LanguageManager.get_text("paint_color_btn"))
        self.brush_size_slider.config(label=LanguageManager.get_text("paint_brush_size"))
        self.btn_text.config(text=LanguageManager.get_text("paint_text_btn"))

    def on_close(self):
        """Отписка от наблюдателя языка при закрытии."""
        LanguageManager.remove_observer(self)
        self.destroy()

    # ---------------- отмена / возврат ----------------
    def _push_undo(self, snapshot=None):
        """Снимок текущего image в стек отмены; новое действие очищает стек возврата."""
        snap = snapshot if snapshot is not None else self.image.copy()
        self._undo_stack.append(snap)
        if len(self._undo_stack) > self.UNDO_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        """Отменяет последнее действие (мазок, текст, ластик, сдвиг, зеркало)."""
        if not self._undo_stack:
            self.status_var.set("Отменять нечего")
            return
        self._redo_stack.append(self.image.copy())
        self.image = self._undo_stack.pop()
        self._after_image_change("Отменено")

    def redo(self):
        """Возвращает отменённое действие."""
        if not self._redo_stack:
            self.status_var.set("Возвращать нечего")
            return
        self._undo_stack.append(self.image.copy())
        self.image = self._redo_stack.pop()
        self._after_image_change("Возвращено")

    def _after_image_change(self, note):
        """Общая реакция на смену кадра: сброс кеша подложки и перерисовка."""
        self._checker_cache = None          # размер мог измениться после сдвига/зеркала
        self._last_pixel = None
        self.update_canvas()
        self.status_var.set(f"{note}    кадр {self.image.width}×{self.image.height}    отмена: {len(self._undo_stack)}    возврат: {len(self._redo_stack)}")

    # ---------------- трансформации кадра ----------------
    def flip_horizontal(self):
        """Зеркалит кадр по горизонтали."""
        self._push_undo()
        self.image = self.image.transpose(Image.FLIP_LEFT_RIGHT)
        self._after_image_change("Зеркало")

    def shift_image(self, dx, dy):
        """Сдвигает кадр на (dx, dy) пикселей; освободившееся — прозрачное."""
        self._push_undo()
        shifted = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        shifted.paste(self.image, (dx, dy))
        self.image = shifted
        self._after_image_change(f"Сдвиг ({dx:+d}, {dy:+d})")

    # ---------------- масштаб ----------------
    def set_zoom(self, value):
        """Масштаб из ползунка (вызывается и колесом через zoom_slider.set)."""
        self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, int(float(value))))
        self.update_canvas()

    def on_mouse_wheel(self, event):
        """Колесо мыши: шаг масштаба ±1."""
        step = 1 if event.delta > 0 else -1
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.zoom + step))
        if new_zoom != self.zoom:
            self.zoom_slider.set(new_zoom)   # set вызовет set_zoom -> update_canvas

    # ---------------- режимы ----------------
    def toggle_eraser(self):
        """Включает/выключает режим ластика."""
        self.eraser_mode = not self.eraser_mode
        if self.eraser_mode and self.pipette_mode:
            self.toggle_pipette()          # два режима одновременно не нужны
        if self.eraser_mode:
            self.btn_eraser.config(relief=tk.SUNKEN, bg="#ffcc80", text="Ластик: ВКЛ")
        else:
            self.btn_eraser.config(relief=tk.RAISED, bg=self._btn_eraser_bg, text="Ластик")

    def toggle_pipette(self):
        """Включает/выключает пипетку: клик по кадру берёт цвет в кисть."""
        self.pipette_mode = not self.pipette_mode
        if self.pipette_mode:
            if self.eraser_mode:           # ластик и пипетка несовместимы
                self.eraser_mode = False
                self.btn_eraser.config(relief=tk.RAISED, bg=self._btn_eraser_bg, text="Ластик")
            self.btn_pipette.config(relief=tk.SUNKEN, bg="#c8e6c9", text="Пипетка: ВКЛ")
            self.canvas.config(cursor="tcross")
        else:
            self.btn_pipette.config(relief=tk.RAISED, bg=self._btn_pipette_bg, text="Пипетка")
            self.canvas.config(cursor="crosshair")

    def toggle_grid(self):
        """Включает/выключает сетку по пикселям."""
        self.grid_enabled = not self.grid_enabled
        if self.grid_enabled:
            self.btn_grid.config(relief=tk.SUNKEN, bg="#b3e5fc", text="Сетка: ВКЛ")
            self.draw_pixel_grid()
        else:
            self.btn_grid.config(relief=tk.RAISED, bg=self._btn_grid_bg, text="Сетка")
            self.canvas.delete("grid")

    def select_color(self):
        """Выбор цвета из палитры."""
        color = colorchooser.askcolor(initialcolor=self.brush_color)
        if color[0] is not None:
            hex_color = color[1] if color[1] else "#%02x%02x%02x" % tuple(int(c) for c in color[0])
            self.set_brush_color(hex_color)

    def set_brush_color(self, hex_color):
        """Единая точка смены цвета: кисть, образец и подпись hex обновляются вместе."""
        self.brush_color = hex_color
        self.color_swatch.config(bg=hex_color)
        self.color_hex_label.config(text=hex_color.upper())

    def pick_color_at(self, event):
        """Пипетка: берёт цвет пикселя под курсором. True — цвет взят."""
        px, py = self.event_to_pixel(event)
        if not (0 <= px < self.image.width and 0 <= py < self.image.height):
            self.status_var.set("Пипетка: клик мимо кадра")
            return False
        px_color = self.image.getpixel((px, py))
        r, g, b = px_color[:3]
        a = px_color[3] if len(px_color) > 3 else 255
        if a == 0:
            self.status_var.set(f"Пипетка: пиксель ({px}, {py}) прозрачный — цвет не взят")
            return False
        hex_color = "#%02x%02x%02x" % (r, g, b)
        self.set_brush_color(hex_color)
        self.status_var.set(f"Пипетка: взят {hex_color.upper()} из ({px}, {py})")
        return True

    def on_alt_click(self, event):
        """Alt+клик — взять цвет, не включая режим пипетки."""
        self.pick_color_at(event)
        return "break"

    def add_text(self):
        """Добавляет текст: ждём клик по холсту, рисуем в этой точке."""
        self.text_mode = True
        self.canvas.create_text(
            self.canvas.winfo_width() // 2, 10,
            text=LanguageManager.get_text("paint_hint"),
            tags="hint", fill="#888888", font=("Arial", 10)
        )

    def place_text(self, event):
        """Рисует текст в точку клика — ВНУТРИ PIL-изображения."""
        if not getattr(self, "text_mode", False):
            return
        text = simpledialog.askstring(LanguageManager.get_text("paint_text_title"),
                                      LanguageManager.get_text("paint_text_prompt"))
        self.text_mode = False
        self.canvas.delete("hint")
        if not text:
            return
        size = simpledialog.askinteger(LanguageManager.get_text("paint_size_title"),
                                       LanguageManager.get_text("paint_size_prompt"),
                                       minvalue=8, maxvalue=200, initialvalue=20)
        if size is None:
            return
        px, py = self.event_to_pixel(event)
        self._push_undo()
        draw = ImageDraw.Draw(self.image)
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except Exception:
            font = ImageFont.load_default(size=size)
        draw.text((px, py), text, font=font, fill=self.brush_color)
        self.update_canvas()

    # ---------------- рисование ----------------
    def event_to_pixel(self, event):
        """Экранная точка -> пиксель кадра (учитывает прокрутку холста и зум)."""
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        return int(cx) // self.zoom, int(cy) // self.zoom

    def on_mouse_down(self, event):
        """Начинает мазок; одиночный клик ставит точку размером с кисть."""
        if getattr(self, "text_mode", False):
            return
        if self.pipette_mode:                       # пипетка: взяли цвет — вернулись к кисти
            if self.pick_color_at(event):
                self.toggle_pipette()
            return
        # один шаг отмены на весь мазок, а не на каждый пиксель
        self._stroke_snapshot = self.image.copy()
        self.last_x, self.last_y = self.event_to_pixel(event)
        self.draw_line(self.last_x, self.last_y, self.last_x, self.last_y)

    def on_mouse_drag(self, event):
        """Продолжает мазок за курсором."""
        if self.last_x is not None and self.last_y is not None:
            px, py = self.event_to_pixel(event)
            self.draw_line(self.last_x, self.last_y, px, py)
            self.last_x, self.last_y = px, py

    def on_mouse_up(self, event):
        """Сбрасывает координаты при отпускании кнопки мыши."""
        if self._stroke_snapshot is not None:
            # снимок кладём в стек только если мазок реально что-то изменил
            if self._stroke_snapshot.tobytes() != self.image.tobytes():
                self._push_undo(self._stroke_snapshot)
            self._stroke_snapshot = None
        self.last_x, self.last_y = None, None

    def draw_line(self, x1, y1, x2, y2):
        """Рисует линию (или точку). Ластик пишет прозрачностью (0,0,0,0).

        Кисть 1 — ровно один пиксель: при r=0 эллипс невидим (пиксель-арт
        требует ставить точку напрямую), поэтому для width==1 — отдельная ветка.
        """
        color = (0, 0, 0, 0) if self.eraser_mode else self.brush_color
        width = max(1, int(self.brush_size_slider.get()))
        draw = ImageDraw.Draw(self.image)

        if width == 1:
            # одиночный пиксель: point не теряется, в отличие от эллипса радиусом 0
            if (x1, y1) == (x2, y2):
                draw.point((x1, y1), fill=color)
            else:
                draw.line([(x1, y1), (x2, y2)], fill=color, width=1)
            self.update_canvas()
            return

        r = width // 2
        if (x1, y1) == (x2, y2):
            draw.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=color)
        else:
            draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
            draw.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], fill=color)  # ровный стык
        self.update_canvas()

    # ---------------- подсветка пикселя ----------------
    def on_mouse_move(self, event):
        """Показывает, какой пиксель под курсором: рамка + координаты и цвет."""
        px, py = self.event_to_pixel(event)
        if 0 <= px < self.image.width and 0 <= py < self.image.height:
            self._last_pixel = (px, py)
            self.draw_cursor_cell()
            px_color = self.image.getpixel((px, py))
            if len(px_color) == 4:
                r, g, b, a = px_color
            else:
                r, g, b = px_color
                a = 255
            alpha_note = "" if a == 255 else ("  (прозрачный)" if a == 0 else f"  alpha {a}")
            self.status_var.set(
                f"x: {px}  y: {py}    #{r:02x}{g:02x}{b:02x}  RGBA({r}, {g}, {b}, {a}){alpha_note}"
                f"    кадр {self.image.width}×{self.image.height}    масштаб ×{self.zoom}"
            )
        else:
            self._last_pixel = None
            self.canvas.delete("cursor_cell")
            self.status_var.set(
                f"вне кадра    кадр {self.image.width}×{self.image.height}    масштаб ×{self.zoom}"
            )

    def draw_cursor_cell(self):
        """Красная рамка вокруг пикселя под курсором (толщина — по масштабу)."""
        self.canvas.delete("cursor_cell")
        if not self._last_pixel:
            return
        px, py = self._last_pixel
        z = self.zoom
        self.canvas.create_rectangle(px * z, py * z, px * z + z, py * z + z,
                                     outline="#ff1744", width=max(1, z // 4),
                                     tags="cursor_cell")

    def on_mouse_leave(self, event):
        """Курсор ушёл с холста — убираем рамку."""
        self._last_pixel = None
        self.canvas.delete("cursor_cell")

    # ---------------- отрисовка холста ----------------
    def checker_base(self, w, h):
        """Подложка-шахматка w×h. Клетка = 2 пикселя кадра (выровнена по сетке пикселей),
        собирается тайлингом плитки 2×2 клетки — не тормозит на больших холстах."""
        c = max(self.MIN_CHECKER, self.zoom * 2)     # клетка = 2 пикселя кадра, но не мельче 4 экранных
        if self._checker_cache and self._checker_cache[0] == (w, h, c):
            return self._checker_cache[1]
        tile = Image.new("RGBA", (c * 2, c * 2), (255, 255, 255, 255))
        td = ImageDraw.Draw(tile)
        td.rectangle([0, 0, c - 1, c - 1], fill=(200, 200, 200, 255))
        td.rectangle([c, c, c * 2 - 1, c * 2 - 1], fill=(200, 200, 200, 255))
        img = Image.new("RGBA", (w, h), (255, 255, 255, 255))
        for y in range(0, h, c * 2):
            for x in range(0, w, c * 2):
                img.paste(tile, (x, y))
        self._checker_cache = ((w, h, c), img)
        return img

    def draw_pixel_grid(self):
        """Линии сетки по границам пикселей кадра (поверх картинки)."""
        self.canvas.delete("grid")
        z = self.zoom
        cells = self.image.width * self.image.height
        if z < 3 or cells > 40000:
            return  # при мелком масштабе сетка сливается, при огромном кадре — тормозит
        w = self.image.width * z
        h = self.image.height * z
        for x in range(0, w + 1, z):
            self.canvas.create_line(x, 0, x, h, fill="#a8a8a8", tags="grid")
        for y in range(0, h + 1, z):
            self.canvas.create_line(0, y, w, y, fill="#a8a8a8", tags="grid")

    def update_canvas(self):
        """Пересобирает холст: шахматка + кадр, затем сетку и подсветку."""
        z = self.zoom
        w, h = self.image.width * z, self.image.height * z

        composed = self.checker_base(w, h).copy()
        scaled = self.image if z == 1 else self.image.resize((w, h), Image.NEAREST)
        composed.alpha_composite(scaled)

        self.tk_image = ImageTk.PhotoImage(composed)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image, tags="base")
        self.canvas.config(scrollregion=(0, 0, w, h))

        if self.grid_enabled:
            self.draw_pixel_grid()
        self.draw_cursor_cell()   # рамка пикселя переживает перерисовку холста