import tkinter as tk
from PIL import Image, ImageTk
import logging


class ImageGrid(tk.Canvas):
    def __init__(self, master, atlas_image, **kwargs):
      
        super().__init__(master, **kwargs)
        self.master = master
        self.atlas_image = atlas_image
        self.grid_enabled = False  # По умолчанию сетка выключена

         # Упаковываем Canvas с правильными параметрами
        self.pack(fill=tk.BOTH, expand=True)


        # Переменные для масштабирования
        self.scale_factor = 1.0
        self.scale_delta = 0.01  # Шаг масштабирования

        # Настройка логирования
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(message)s",
            filename="image_grid.log",
            filemode="w",
        )
        logging.info("Инициализация ImageGrid")

        print(f"ImageGrid получает изображение: {self.atlas_image.size if self.atlas_image else 'Нет'}")

        # Отображение изображения на Canvas
        self.tk_image = None
        self.image_on_canvas = None
        logging.debug("Изображение отображено на Canvas")

        # Инициализация изображения
        self.update_image(self.atlas_image)

        # Переменные для сетки
        self.grid_size = 50  # Размер сетки по умолчанию (в пикселях)
        self.grid_color = "blue"

        # Переменные для выделения области
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None

        # Основной кадр (по умолчанию None)
        self.main_frame = None
        self.main_frame_id = None
         
        # Привязка событий
        self.bind_events()
        

        # Принудительно включаем сетку
        self.draw_grid()  # Отрисовываем сетку сразу после инициализации

        # Первоначальная отрисовка сетки
        self.after(100, self.draw_grid)  # Даём время на отрисовку окна

        print(f"Изображение в ImageGrid: {self.atlas_image.size}")  


    def draw_grid(self):
        """Отрисовывает сетку на изображении."""
        logging.debug("Начало отрисовки сетки")
        self.delete("grid")  # Удаляем старую сетку

        if not self.grid_enabled:
            logging.debug("Сетка отключена, отрисовка пропущена")
            return

        width = self.winfo_width()
        height = self.winfo_height()

        logging.debug(f"Размеры Canvas: ширина={width}, высота={height}")
        #logging.debug(f"Размер сетки: {self.grid_size} пикселей")

        if width <= 1 or height <= 1:  # Добавить проверку
            self.after(100, self.draw_grid)
            return

        grid_step = int(self.grid_size * self.scale_factor)  # Теперь grid_size - это число

        # Рисуем вертикальные линии
        for x in range(0, width, grid_step):
            self.create_line(x, 0, x, height, fill=self.grid_color, tags="grid")
            #logging.debug(f"Вертикальная линия: x={x}")

        # Рисуем горизонтальные линии
        for y in range(0, height, int(grid_step)):
            self.create_line(0, y, width, y, fill=self.grid_color, tags="grid")
            #logging.debug(f"Горизонтальная линия: y={y}")

        logging.info(f"Сетка отрисована с размером {self.grid_size} пикселей")
        self.update()  # Принудительно обновляем Canvas

    def toggle_grid(self):
        """Включает/выключает отображение сетки."""
        self.grid_enabled = not self.grid_enabled
        logging.info(f"Сетка {'включена' if self.grid_enabled else 'выключена'}")
        if self.grid_enabled:
            self.draw_grid()
        else:
            self.delete("grid")  # Удаляем сетку

    def set_grid_size(self, size):
        """Устанавливает размер сетки."""
        logging.debug(f"Установка размера сетки: {size} пикселей")
        self.grid_size = size
        self.draw_grid()
        logging.info(f"Размер сетки изменен на {size} пикселей")

    def on_mouse_wheel(self, event):
        """Обрабатывает масштабирование колесиком мыши."""
        if event.delta > 0:
            self.scale_factor *= 1.1  # Увеличение
            logging.debug("Масштабирование: увеличение")
        else:
            self.scale_factor *= 0.9  # Уменьшение
            logging.debug("Масштабирование: уменьшение")

        # Ограничиваем масштабирование
        self.scale_factor = max(0.1, min(self.scale_factor, 5.0))
        logging.debug(f"Текущий масштаб: {self.scale_factor}")

        # Масштабируем изображение и сетку
        self.update_scale()  # Перерисовываем сетку после масштабирования
        logging.debug("Сетка перерисована после масштабирования")

    def update_scale(self):
        """Обновляет масштаб изображения и сетки."""
        # Масштабируем изображение
        new_width = int(self.atlas_image.width * self.scale_factor)
        new_height = int(self.atlas_image.height * self.scale_factor)
        resized_image = self.atlas_image.resize((new_width, new_height), Image.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized_image)
        self.itemconfig(self.image_on_canvas, image=self.tk_image)

        # Масштабируем сетку
        if self.grid_enabled:
            self.draw_grid()

    def get_selection_coords(self):
        """Возвращает координаты выделенной области."""
        return self.start_x, self.start_y, self.end_x, self.end_y


    def on_mouse_down(self, event):
        """Обрабатывает нажатие левой кнопки мыши."""
        self.start_x = event.x
        self.start_y = event.y
        logging.debug(f"Нажатие мыши: ({self.start_x}, {self.start_y})")

    def on_mouse_drag(self, event):
        """Обрабатывает перемещение с зажатой левой кнопкой мыши."""
        self.end_x = event.x
        self.end_y = event.y
        self.draw_selection()
        logging.debug(f"Перемещение мыши: ({self.end_x}, {self.end_y})")

    def on_mouse_up(self, event):
        """Обрабатывает отпускание левой кнопки мыши."""
        self.end_x = event.x
        self.end_y = event.y
        self.draw_selection()
        logging.debug(f"Отпускание мыши: ({self.end_x}, {self.end_y})")
        # Здесь можно добавить логику для сохранения выделенной области

    def draw_selection(self):
        """Отрисовка прямоугольника выделения."""
        self.delete("selection")  # Удаляем предыдущее выделение
        if hasattr(self, "selection"):
            self.delete("selection")  # Удаляем предыдущее выделение только если оно существует
        if self.start_x is not None and self.start_y is not None and self.end_x is not None and self.end_y is not None:
            self.create_rectangle(
                self.start_x, self.start_y, self.end_x, self.end_y,
                outline="red", tags="selection"
            )
            logging.debug(f"Прямоугольник выделения: ({self.start_x}, {self.start_y}) -> ({self.end_x}, {self.end_y})")
    
    def bind_events(self):
        """Привязывает события мыши"""
        self.bind("<MouseWheel>", self.on_mouse_wheel)
        self.bind("<ButtonPress-1>", self.on_mouse_down)
        self.bind("<B1-Motion>", self.on_mouse_drag)
        self.bind("<ButtonRelease-1>", self.on_mouse_up)


    def update_image(self, new_image):

        if new_image is None:
            print("Ошибка: Передано пустое изображение")
            return
        
        if not isinstance(new_image, Image.Image):
            print(f"Ошибка: Неверный тип изображения: {type(new_image)}")
            return

        print(f"Обновление изображения, размер: {new_image.size}")

        """Обновляет изображение с сохранением масштаба"""
        self.atlas_image = new_image

        try:
            # Масштабируем изображение
            width = int(self.atlas_image.width * self.scale_factor)
            height = int(self.atlas_image.height * self.scale_factor)
            resized = self.atlas_image.resize((width, height), Image.LANCZOS)
        
            # Сохраняем PhotoImage
            self.tk_image = ImageTk.PhotoImage(resized)

            if self.image_on_canvas is not None:
                self.itemconfig(self.image_on_canvas, image=self.tk_image)
            else:
                self.image_on_canvas = self.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        
            self.config(scrollregion=self.bbox(tk.ALL))

            print(f"Обновление изображения, размер: {new_image.size}")

            # Перерисовываем сетку
            if self.grid_enabled:
                self.draw_grid()

        except Exception as e:
            print(f"Ошибка при обновлении изображения: {str(e)}")
