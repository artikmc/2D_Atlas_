import tkinter as tk
from tkinter import colorchooser, simpledialog
from PIL import Image, ImageTk, ImageDraw


class PaintApp(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Paint Application")

        self.brush_color = "black"
        self.brush_size = 5
        self.last_x, self.last_y = None, None
        
        self.image = Image.new("RGBA", (800, 600), (255, 255, 255))
        self.tk_image = ImageTk.PhotoImage(self.image)

        self.canvas = tk.Canvas(self, width=800, height=600)
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)

        self.create_widgets()
        self.bind_events()

    def create_widgets(self):
        """Создает элементы управления для рисования."""
        control_frame = tk.Frame(self)
        control_frame.pack(side=tk.TOP, fill=tk.X)

        # Выбор цвета
        btn_color = tk.Button(control_frame, text="Color", command=self.select_color)
        btn_color.pack(side=tk.LEFT)

        # Слайдер размера кисти
        self.brush_size_slider = tk.Scale(control_frame, from_=1, to=100, orient=tk.HORIZONTAL, label="Brush Size")
        self.brush_size_slider.set(self.brush_size)
        self.brush_size_slider.pack(side=tk.LEFT)

        # Кнопка текста
        btn_text = tk.Button(control_frame, text="Text", command=self.add_text)
        btn_text.pack(side=tk.LEFT)

    def bind_events(self):
        """Привязывает события мыши к функции рисования."""
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

    def select_color(self):
        """Выбор цвета для рисования."""
        color = colorchooser.askcolor()
        if color[1] is not None:
            self.brush_color = color[1]

    def add_text(self):
        """Добавляет текст на холст."""
        text = simpledialog.askstring("Input Text", "Введите текст:")
        if text:
            x = self.canvas.winfo_width() // 2
            y = self.canvas.winfo_height() // 2
            self.canvas.create_text(x, y, text=text, fill=self.brush_color, font=("Arial", 20))

    def on_mouse_down(self, event):
        """Обработчик нажатия кнопки мыши для начала рисования."""
        self.last_x, self.last_y = event.x, event.y

    def on_mouse_drag(self, event):
        """Обработчик перетаскивания мыши для рисования."""
        if self.last_x is not None and self.last_y is not None:
            self.draw_line(self.last_x, self.last_y, event.x, event.y)
            self.last_x, self.last_y = event.x, event.y

    def on_mouse_up(self, event):
        """Сбрасывает координаты при отпускании кнопки мыши."""
        self.last_x, self.last_y = None, None

    def draw_line(self, x1, y1, x2, y2):
        """Рисует линию на холсте."""
        with ImageDraw.Draw(self.image) as draw:
            draw.line([(x1, y1), (x2, y2)], fill=self.brush_color, width=self.brush_size_slider.get())

        self.update_canvas()

    def update_canvas(self):
        """Обновляет отображение изображения на холсте."""
        self.tk_image = ImageTk.PhotoImage(self.image)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)