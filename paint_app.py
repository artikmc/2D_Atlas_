import tkinter as tk
from tkinter import colorchooser, simpledialog
from PIL import Image, ImageTk, ImageDraw, ImageFont
from language_manager import LanguageManager


class PaintApp(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title(LanguageManager.get_text("paint_title"))

        self.brush_color = "black"
        self.brush_size = 5
        self.last_x, self.last_y = None, None
        self.text_mode = False

        self.image = Image.new("RGBA", (800, 600), (255, 255, 255))
        self.tk_image = ImageTk.PhotoImage(self.image)

        self.canvas = tk.Canvas(self, width=800, height=600)
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)

        self.create_widgets()
        self.bind_events()

        LanguageManager.add_observer(self)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_widgets(self):
        """Создает элементы управления для рисования."""
        control_frame = tk.Frame(self)
        control_frame.pack(side=tk.TOP, fill=tk.X)

        self.btn_color = tk.Button(control_frame, command=self.select_color)
        self.btn_color.pack(side=tk.LEFT)

        self.brush_size_slider = tk.Scale(control_frame, from_=1, to=100, orient=tk.HORIZONTAL)
        self.brush_size_slider.set(self.brush_size)
        self.brush_size_slider.pack(side=tk.LEFT)

        self.btn_text = tk.Button(control_frame, command=self.add_text)
        self.btn_text.pack(side=tk.LEFT)

        self.update_texts()

    def bind_events(self):
        """Привязывает события мыши к функции рисования."""
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up, add="+")
        self.canvas.bind("<ButtonRelease-1>", self.place_text, add="+")

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

    def select_color(self):
        """Выбор цвета для рисования."""
        color = colorchooser.askcolor()
        if color[0] is not None:
            self.brush_color = color[1] if color[1] else "#%02x%02x%02x" % tuple(int(c) for c in color[0])

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
        draw = ImageDraw.Draw(self.image)
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except Exception:
            font = ImageFont.load_default(size=size)
        draw.text((event.x, event.y), text, font=font, fill=self.brush_color)
        self.update_canvas()

    def on_mouse_down(self, event):
        """Обрабатывает нажатие кнопки мыши для начала рисования."""
        if getattr(self, "text_mode", False):
            return
        self.last_x, self.last_y = event.x, event.y

    def on_mouse_drag(self, event):
        """Обрабатывает перемещение с зажатой левой кнопкой мыши."""
        if self.last_x is not None and self.last_y is not None:
            self.draw_line(self.last_x, self.last_y, event.x, event.y)
            self.last_x, self.last_y = event.x, event.y

    def on_mouse_up(self, event):
        """Сбрасывает координаты при отпускании кнопки мыши."""
        self.last_x, self.last_y = None, None

    def draw_line(self, x1, y1, x2, y2):
        """Рисует линию на холсте."""
        draw = ImageDraw.Draw(self.image)
        draw.line([(x1, y1), (x2, y2)], fill=self.brush_color, width=self.brush_size_slider.get())
        self.update_canvas()

    def update_canvas(self):
        """Обновляет отображение изображения на холсте."""
        self.tk_image = ImageTk.PhotoImage(self.image)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)