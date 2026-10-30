import tkinter as tk
from PIL import Image, ImageTk
import logging
from frame_detector import detect_frames


class ImageGrid(tk.Canvas):
    """Экран атласа: зум колесом, выделение рамкой, слой «Авто-сетка» (детекция рядов/кадров).

    ВАЖНО: координаты выделения хранятся в пикселях ОРИГИНАЛЬНОГО изображения (atlas_image),
    а не экрана. Крой в ImageSplitter работает по оригиналу — значит выделение корректно
    при любом масштабе. Для отрисовки на канвасе координаты пересчитываются.
    """

    def __init__(self, master, atlas_image, **kwargs):
        super().__init__(master, **kwargs)
        self.master = master
        self.atlas_image = atlas_image
        self.grid_enabled = False  # обычная равная сетка — выключена

        self.pack(fill=tk.BOTH, expand=True)

        # Масштабирование
        self.scale_factor = 1.0

        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(message)s",
            filename="image_grid.log",
            filemode="w",
        )
        logging.info("Инициализация ImageGrid")

        # Авто-сетка (детекция)
        self.auto_grid_enabled = False
        self.detected_rows = []  # кэш detect_frames(atlas_image) в координатах оригинала


        # Отображение изображения
        self.tk_image = None
        self.image_on_canvas = None
        self.update_image(self.atlas_image)

        # Равная сетка
        self.grid_size = 50
        self.grid_color = "blue"

        # Выделение — в координатах ОРИГИНАЛА
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None
        self._down_canvas = None  # точка нажатия в координатах канваса (для клика-выбора ряда)

        self.bind_events()

        self.draw_grid()
        self.after(100, self.draw_grid)

        print(f"Изображение в ImageGrid: {self.atlas_image.size}")

    # ---------- конвертеры координат ----------
    def image_to_canvas(self, x, y):
        """Точка оригинала -> точка канваса (изображение нарисовано с anchor NW в (0,0))."""
        return x * self.scale_factor, y * self.scale_factor

    def canvas_to_image(self, x, y):
        """Точка канваса -> точка оригинала."""
        sf = self.scale_factor if self.scale_factor else 1.0
        return x / sf, y / sf

    # ---------- равная сетка (прежнее поведение) ----------
    def draw_grid(self):
        """Отрисовывает равную сетку на изображении."""
        self.delete("grid")
        if not self.grid_enabled:
            return
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            self.after(100, self.draw_grid)
            return
        grid_step = max(1, int(self.grid_size * self.scale_factor))
        for x in range(0, width, grid_step):
            self.create_line(x, 0, x, height, fill=self.grid_color, tags="grid")
        for y in range(0, height, grid_step):
            self.create_line(0, y, width, y, fill=self.grid_color, tags="grid")
        self.update()

    def toggle_grid(self):
        self.grid_enabled = not self.grid_enabled
        if self.grid_enabled:
            self.draw_grid()
        else:
            self.delete("grid")

    def set_grid_size(self, size):
        self.grid_size = size
        self.draw_grid()

    # ---------- авто-сетка (детекция) ----------
    def toggle_auto_grid(self):
        """Включает/выключает слой детекции. Возвращает новое состояние."""
        self.auto_grid_enabled = not self.auto_grid_enabled
        if self.auto_grid_enabled:
            self.detect_auto_grid()
        self.draw_auto_grid()
        return self.auto_grid_enabled

    def detect_auto_grid(self):
        """Один проход детекции по всему атласу; кэш в координатах оригинала."""
        try:
            self.detected_rows = detect_frames(self.atlas_image)["rows"]
            n = sum(len(r["frames"]) for r in self.detected_rows)
            print(f"Авто-сетка: найдено {len(self.detected_rows)} рядов, {n} кадров.")
        except Exception as e:
            print(f"Ошибка детекции: {e}")
            self.detected_rows = []

    def draw_auto_grid(self):
        """Рисует рамки детектированных рядов/кадров, пересчитывая их под текущий масштаб."""
        self.delete("autogrid")
        if not self.auto_grid_enabled:
            return
        for ri, row in enumerate(self.detected_rows, 1):
            ry0, ry1 = self.image_to_canvas(0, row["y0"])
            _, cy1 = self.image_to_canvas(0, row["y1"] + 1)
            cx1, _ = self.image_to_canvas(self.atlas_image.width, 0)
            self.create_rectangle(0, ry0, cx1, cy1, outline="#b36bff", width=1, tags="autogrid")
            for fi, (fx0, fx1) in enumerate(row["frames"], 1):
                x0, y0 = self.image_to_canvas(max(0, fx0 - 2), row["y0"])
                x1, y1 = self.image_to_canvas(min(self.atlas_image.width, fx1 + 3), row["y1"] + 1)
                self.create_rectangle(x0, y0, x1, y1, outline="#00c853", width=1, tags="autogrid")
                self.create_text((x0 + x1) / 2, y0 - 2, anchor=tk.S, text=f"{ri}.{fi}",
                                 fill="#00c853", font=("Arial", 8, "bold"), tags="autogrid")

    def _row_at(self, x_img, y_img):
        """Ряд детекции, содержащий точку оригинала, или None."""
        for row in self.detected_rows:
            if row["y0"] <= y_img <= row["y1"] + 1:
                return row
        return None

    # ---------- зум ----------
    def on_mouse_wheel(self, event):
        if event.delta > 0:
            self.scale_factor *= 1.1
        else:
            self.scale_factor *= 0.9
        self.scale_factor = max(0.1, min(self.scale_factor, 5.0))
        self.update_scale()

    def update_scale(self):
        """Перерисовывает изображение, сетку, авто-сетку и выделение под новый масштаб."""
        new_width = max(1, int(self.atlas_image.width * self.scale_factor))
        new_height = max(1, int(self.atlas_image.height * self.scale_factor))
        resized_image = self.atlas_image.resize((new_width, new_height), Image.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized_image)
        self.itemconfig(self.image_on_canvas, image=self.tk_image)

        if self.grid_enabled:
            self.draw_grid()
        if self.auto_grid_enabled:
            self.draw_auto_grid()
        self.draw_selection()
        self.config(scrollregion=self.bbox(tk.ALL))

    # ---------- выделение (в координатах оригинала) ----------
    def get_selection_coords(self):
        """Координаты выделения в пикселях ОРИГИНАЛА — годятся для crop напрямую."""
        if None in (self.start_x, self.start_y, self.end_x, self.end_y):
            return None, None, None, None
        return (int(round(self.start_x)), int(round(self.start_y)),
                int(round(self.end_x)), int(round(self.end_y)))

    def on_mouse_down(self, event):
        x_img, y_img = self.canvas_to_image(event.x, event.y)
        self.start_x, self.start_y = x_img, y_img
        self.end_x, self.end_y = x_img, y_img
        self._down_canvas = (event.x, event.y)

    def on_mouse_drag(self, event):
        self.end_x, self.end_y = self.canvas_to_image(event.x, event.y)
        self.draw_selection()

    def on_mouse_up(self, event):
        self.end_x, self.end_y = self.canvas_to_image(event.x, event.y)
        # Клик без протяжки при включённой авто-сетке: выделяем целый ряд детекции
        if self.auto_grid_enabled and self._down_canvas is not None:
            dx = abs(event.x - self._down_canvas[0])
            dy = abs(event.y - self._down_canvas[1])
            if dx < 5 and dy < 5:
                row = self._row_at(self.end_x, self.end_y)
                if row:
                    w = self.atlas_image.width
                    self.start_x, self.start_y = 0, row["y0"]
                    self.end_x, self.end_y = w, row["y1"] + 1
                    print(f"Клик: выбран ряд y={row['y0']}..{row['y1']} "
                          f"({len(row['frames'])} кадров).")
        self.draw_selection()

    def draw_selection(self):
        """Прямоугольник выделения: хранимые оригинал-координаты -> канвас."""
        self.delete("selection")
        if None in (self.start_x, self.start_y, self.end_x, self.end_y):
            return
        x0, y0 = self.image_to_canvas(min(self.start_x, self.end_x), min(self.start_y, self.end_y))
        x1, y1 = self.image_to_canvas(max(self.start_x, self.end_x), max(self.start_y, self.end_y))
        self.create_rectangle(x0, y0, x1, y1, outline="red", width=2, tags="selection")

    def bind_events(self):
        self.bind("<MouseWheel>", self.on_mouse_wheel)
        self.bind("<ButtonPress-1>", self.on_mouse_down)
        self.bind("<B1-Motion>", self.on_mouse_drag)
        self.bind("<ButtonRelease-1>", self.on_mouse_up)

    # ---------- смена изображения ----------
    def update_image(self, new_image):
        if new_image is None:
            print("Ошибка: Передано пустое изображение")
            return
        if not isinstance(new_image, Image.Image):
            print(f"Ошибка: Неверный тип изображения: {type(new_image)}")
            return

        self.atlas_image = new_image
        try:
            width = max(1, int(self.atlas_image.width * self.scale_factor))
            height = max(1, int(self.atlas_image.height * self.scale_factor))
            resized = self.atlas_image.resize((width, height), Image.LANCZOS)
            self.tk_image = ImageTk.PhotoImage(resized)

            if self.image_on_canvas is not None:
                self.itemconfig(self.image_on_canvas, image=self.tk_image)
            else:
                self.image_on_canvas = self.create_image(0, 0, anchor=tk.NW, image=self.tk_image)

            self.config(scrollregion=self.bbox(tk.ALL))

            if self.grid_enabled:
                self.draw_grid()
            if self.auto_grid_enabled:
                self.detect_auto_grid()
                self.draw_auto_grid()
            self.draw_selection()
        except Exception as e:
            print(f"Ошибка при обновлении изображения: {str(e)}")
