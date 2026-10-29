import tkinter as tk
from PIL import Image, ImageTk, ImageChops
from io import BytesIO
from database import create_connection, insert_frame
from tkinter import filedialog, messagebox
from paint_app import PaintApp
from frame_detector import detect_frames

class AnimationViewer(tk.Toplevel):
    def __init__(self, master, last_selected_region, class_name, main_frame_id, character_id=None):
        super().__init__(master)
        self.title(f"Анимация: {class_name} | основной кадр #{main_frame_id} | персонаж #{character_id}")
        self.class_name = class_name
        
        self.update()  # Обновляем окно для отображения
        self.selected_region = last_selected_region  # Выделенная область
        self.main_frame_id = main_frame_id  # ID основного кадра
        self.character_id = character_id    # ID персонажа 
        self.frames = []  # Список для хранения кадров
        self.frames_pil = []  # Список PIL.Image кадров — источник для сохранения в БД
        self.current_frame_index = 0  # Индекс текущего кадра
        self.delay = 200  # Задержка между кадрами (в миллисекундах)
        self.is_animating = False  # Флаг для отслеживания состояния анимации (добавлено)

        # Создаем виджеты
        self.create_widgets()

    def create_widgets(self):      
        # Canvas для отображения кадров
        self.canvas = tk.Canvas(self, width=self.selected_region.width,
                                height=self.selected_region.height)
        self.canvas.pack()

        # Слайдер для настройки количества кадров
        self.num_frames_slider = tk.Scale(self, from_=1, to=10, orient=tk.HORIZONTAL,
                                          label="Количество кадров")
        self.num_frames_slider.set(4)
        self.num_frames_slider.pack(pady=5)
        # после установки значения вешаем команду — чтобы не дёрнулось при инициализации
        self.num_frames_slider.configure(command=lambda v: self.draw_split_preview())

        # Слайдер для изменения скорости анимации
        self.speed_slider = tk.Scale(self, from_=100, to=500, orient=tk.HORIZONTAL,
                                     label="Скорость (мс)")
        self.speed_slider.set(200)
        self.speed_slider.pack(pady=5)

        # Счётчик кадра и плёнка нарезки
        self.frame_label = tk.Label(self, text="Двигайте слайдер — линии покажут рез")
        self.frame_label.pack()
        self.strip_canvas = tk.Canvas(self, height=76, highlightthickness=0)
        self.strip_canvas.pack(fill=tk.X, padx=6, pady=4)
        self.strip_canvas.bind("<Button-1>", self.on_strip_click)
        self.strip_photos = []   # держим ссылки на миниатюры от сборщика мусора
        self.strip_cells = []    # координаты ячеек плёнки для подсветки

        # Кнопки для управления
        self.create_buttons()

        # Кнопки для редактирования кадров
        #self.create_edit_buttons()

        self.draw_split_preview()  # показать полосу с линиями реза сразу

    def create_buttons(self):
        """Создает кнопки управления."""
        button_frame = tk.Frame(self)
        button_frame.pack(pady=10)

        # Кнопка для разделения на кадры
        btn_split_frames = tk.Button(button_frame, text="Разделить на кадры", command=self.split_frames)
        btn_split_frames.pack(side=tk.LEFT, padx=5)

        # Кнопка для сохранения кадров
        btn_save_frames = tk.Button(button_frame, text="Сохранить кадры", command=self.save_frames)
        btn_save_frames.pack(side=tk.LEFT, padx=5)

        # Кнопки для управления анимацией
        btn_start = tk.Button(button_frame, text="Запустить анимацию", command=self.start_animation)
        btn_start.pack(side=tk.LEFT, padx=5)

        btn_stop = tk.Button(button_frame, text="Остановить анимацию", command=self.stop_animation)
        btn_stop.pack(side=tk.LEFT, padx=5)

        btn_next = tk.Button(button_frame, text="Следующий кадр", command=self.next_frame)
        btn_next.pack(side=tk.LEFT, padx=5)

        btn_prev = tk.Button(button_frame, text="Предыдущий кадр", command=self.prev_frame)
        btn_prev.pack(side=tk.LEFT, padx=5)

        # Кнопки для дополнительных функций
        btn_save = tk.Button(button_frame, text="Сохранить анимацию", command=self.save_animation)
        btn_save.pack(side=tk.LEFT, padx=5)

        btn_open_paint = tk.Button(button_frame, text="Редактировать", command=self.open_paint)
        btn_open_paint.pack(side=tk.LEFT)


        btn_back = tk.Button(button_frame, text="Вернуться", command=self.destroy)
        btn_back.pack(side=tk.LEFT, padx=5)

      
    
    def create_edit_buttons(self):
        """Создает кнопки для редактирования кадров."""
        edit_frame = tk.Frame(self)
        edit_frame.pack(pady=10)

        btn_crop = tk.Button(edit_frame, text="Обрезать", command=self.crop_frame)
        btn_crop.pack(side=tk.LEFT, padx=5)

        btn_rotate = tk.Button(edit_frame, text="Повернуть", command=self.rotate_frame)
        btn_rotate.pack(side=tk.LEFT, padx=5)

    def draw_split_preview(self):
        """Предпросмотр: линии реза — там, где их реально сделает split_frames."""
        if self.frames_pil:
            self.split_frames()
            return
        self.canvas.delete("all")
        self.tk_image = ImageTk.PhotoImage(self.selected_region)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        w, h = self.selected_region.size

        detected = detect_frames(self.selected_region)
        if detected["rows"]:
            row = max(detected["rows"], key=lambda r: len(r["frames"]))
            y0, y1 = row["y0"], row["y1"] + 1
            self.canvas.create_rectangle(0, y0, w, y1, outline="#00ff7f", width=2)
            for i, (fx0, fx1) in enumerate(row["frames"], 1):
                self.canvas.create_line(fx0 - 2, y0, fx0 - 2, y1, fill="#00ff7f", dash=(4, 2))
                self.canvas.create_line(fx1 + 3, y0, fx1 + 3, y1, fill="#00ff7f", dash=(4, 2))
                self.canvas.create_text((fx0 + fx1) // 2, max(8, y0 - 6), text=str(i),
                                        fill="#00ff7f", font=("Arial", 10, "bold"))
            self.frame_label.config(text=f"Детекция видит {len(row['frames'])} кадров — жмите «Разделить»")
        else:
            n = self.num_frames_slider.get()
            fw = w // n
            for i in range(1, n):
                self.canvas.create_line(i * fw, 0, i * fw, h, fill="#00ff7f", width=2, dash=(4, 2))
            for i in range(n):
                self.canvas.create_text(i * fw + fw // 2, 12, text=str(i + 1),
                                        fill="#00ff7f", font=("Arial", 11, "bold"))
            self.frame_label.config(text=f"Кадры не детектятся — равный рез на {n}")

    def build_filmstrip(self):
        """Строим плёнку: все кадры миниатюрами, клик = показать кадр."""
        self.strip_canvas.delete("all")
        self.strip_photos = []
        self.strip_cells = []
        if not self.frames_pil:
            return
        n = len(self.frames_pil)
        avail_w = max(100, self.strip_canvas.winfo_width() - 8)
        cell = max(24, min(80, avail_w // n))
        x = 6
        for i, fr in enumerate(self.frames_pil):
            scale = min(cell / fr.width, 60 / fr.height)
            thumb = fr.resize((max(1, int(fr.width * scale)),
                               max(1, int(fr.height * scale))), Image.NEAREST)
            photo = ImageTk.PhotoImage(thumb)
            self.strip_photos.append(photo)
            x0, y0, x1, y1 = x, 4, x + cell, 68
            self.strip_canvas.create_rectangle(x0, y0, x1, y1, outline="#555555",
                                               tags=f"cell_{i}")
            self.strip_canvas.create_image((x0 + x1) // 2, (y0 + y1) // 2,
                                           image=photo, tags=f"cell_{i}")
            self.strip_canvas.create_text((x0 + x1) // 2, 72, text=str(i + 1),
                                          fill="#aaaaaa")
            self.strip_cells.append((x0, y0, x1, y1))
            x += cell + 6

    def on_strip_click(self, event):
        """Клик по плёнке — показать выбранный кадр."""
        for i, (x0, y0, x1, y1) in enumerate(self.strip_cells):
            if x0 - 2 <= event.x <= x1 + 2 and 0 <= event.y <= 76:
                self.show_frame(i)
                return
    
    def split_frames(self):
        """Разделяет выделенную область на кадры: по детекции; если она не видит — по слайдеру."""
        width, height = self.selected_region.size
        self.frames = []
        self.frames_pil = []

        detected = detect_frames(self.selected_region)
        if detected["rows"]:
            # если в выделении несколько полос — берём самую «многослойную»
            row = max(detected["rows"], key=lambda r: len(r["frames"]))
            y0 = max(0, row["y0"])
            y1 = min(height - 1, row["y1"])
            for (fx0, fx1) in row["frames"]:
                left = max(0, fx0 - 2)                    # чуть воздуха по бокам
                right = min(width, fx1 + 3)               # x1 включительно + 2px
                frame = self.selected_region.crop((left, y0, right, y1 + 1))
                self.frames_pil.append(frame)
                self.frames.append(ImageTk.PhotoImage(frame))
            print(f"Разделено по детекции: {len(self.frames)} кадров (ширины {[f.width for f in self.frames_pil]}).")
        else:
            num_frames = self.num_frames_slider.get()     # запасной путь: равные куски
            frame_width = width // num_frames
            for i in range(num_frames):
                left = i * frame_width
                right = (i + 1) * frame_width
                frame = self.selected_region.crop((left, 0, right, height))
                self.frames_pil.append(frame)
                self.frames.append(ImageTk.PhotoImage(frame))
            print(f"Детекция не сработала — разделено на {num_frames} равных кадров.")

        if self.frames:
            self.build_filmstrip()
            self.show_frame(0)

    def show_frame(self, index):
        """Отображает кадр по центру canvas, подогнанным по размеру."""
        if not (0 <= index < len(self.frames_pil)):
            return
        self.current_frame_index = index
        frame = self.frames_pil[index]
        cw = int(self.canvas.cget("width"))
        ch = int(self.canvas.cget("height"))
        # Подгоняем кадр под окно с сохранением пропорций (NEAREST — чтобы пиксели не мылились)
        scale = min(cw / frame.width, ch / frame.height)
        if scale != 1:
            frame = frame.resize((max(1, int(frame.width * scale)),
                                  max(1, int(frame.height * scale))), Image.NEAREST)
        photo = ImageTk.PhotoImage(frame)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=photo)
        self.canvas.image = photo  # держим ссылку от сборщика мусора
        self.strip_canvas.delete("sel_rect")
        if index < len(self.strip_cells):
            sx0, sy0, sx1, sy1 = self.strip_cells[index]
            self.strip_canvas.create_rectangle(sx0 - 2, sy0 - 2, sx1 + 2, sy1 + 2,
                                               outline="#00ff7f", width=2, tags="sel_rect")
        self.frame_label.config(text=f"Кадр {index + 1}/{len(self.frames_pil)}")

    def start_animation(self):
        """Запускает анимацию."""
        if not self.is_animating:
            self.is_animating = True
            self.animate()

    def stop_animation(self):
        """Останавливает анимацию."""
        self.is_animating = False

    def animate(self):
        """Отображает кадры в виде анимации."""
        if self.is_animating and self.frames:
            # Отображаем текущий кадр
            self.show_frame(self.current_frame_index)

            # Переходим к следующему кадру
            self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)

            # Повторяем через заданную задержку
            self.after(self.speed_slider.get(), self.animate)

    def open_paint(self):
        """Открывает окно рисования."""
        paint_app = PaintApp(self)  # Создает экземпляр PaintApp
        paint_app.grab_set()  # Запретить взаимодействие с родительским окном, пока открыто рисование
    
    def next_frame(self):
         """Переключает на следующий кадр."""
         if not self.frames:
            return
         self.show_frame((self.current_frame_index + 1) % len(self.frames))

    def prev_frame(self):
        """Переключает на предыдущий кадр."""
        if not self.frames:
            return
        self.show_frame((self.current_frame_index - 1) % len(self.frames))

    def save_frames(self):
        """Сохраняет анимацию в базу данных."""
        if not self.frames:
            print("Ошибка: Нет кадров для сохранения.")
            return

        conn = create_connection()
        if conn is not None:
            for frame in self.frames_pil:
                with BytesIO() as output:
                    frame.save(output, format="PNG")  # PIL пишет валидный PNG в поток
                    frame_data = output.getvalue()
                # Сохраняем кадр с привязкой к основному кадру и персонажу
                insert_frame(conn, self.class_name, frame_data,
                             main_frame_id=self.main_frame_id,
                             character_id=self.character_id)
            conn.close()
            print(f"Кадры сохранены в базу данных для класса '{self.class_name}' с привязкой к основному кадру (ID: {self.main_frame_id}).")
  
   
    def crop_frame(self):
        """Обрезает текущий кадр."""
        if not self.frames:
            print("Ошибка: Нет кадров для обрезки.")
            return

        # Пример: обрезка по центру (можно доработать для интерактивной обрезки)
        current_frame = self.frames[self.current_frame_index]._PhotoImage__photo # Получаем PIL.Image
        cropped_frame = current_frame.crop((50, 50, 150, 150))  # Пример координат
        self.frames[self.current_frame_index] = ImageTk.PhotoImage(cropped_frame)
        self.show_frame(self.current_frame_index)
        print("Кадр обрезан.")

    def rotate_frame(self):
        """Поворачивает текущий кадр."""
        if not self.frames:
            print("Ошибка: Нет кадров для поворота.")
            return

        # Поворот на 90 градусов
        current_frame = self.frames[self.current_frame_index]._PhotoImage__photo  # Получаем PIL.Image
        rotated_frame = current_frame.rotate(90, expand=True)
        self.frames[self.current_frame_index] = ImageTk.PhotoImage(rotated_frame)
        self.show_frame(self.current_frame_index)
        print("Кадр повернут.")
    
    def save_animation(self):
        """
    Сохраняет анимацию в файл.
    """
        if not self.frames:
            messagebox.showerror("Ошибка", "Нет кадров для сохранения.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".gif",
            filetypes=[("GIF files", "*.gif"), ("All files", "*.*")]
    )
        if file_path:
            try:
                # Преобразуем PhotoImage обратно в PIL.Image
                frames = [frame._PhotoImage__photo for frame in self.frames]
                frames[0].save(file_path, save_all=True, append_images=frames[1:], loop=0, duration=self.speed_slider.get())
                messagebox.showinfo("Успех", f"Анимация сохранена в {file_path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить анимацию: {e}")


def remove_empty_space(image, background_color=(255, 255, 255)):
     """Удаляет пустые области (например, белый фон) из изображения."""
     # Создаем изображение с фоном
     bg = Image.new("RGB", image.size, background_color)
     # Находим разницу между фоном и изображением
     diff = ImageChops.difference(image.convert("RGB"), bg)
     # Обрезаем пустые области
     bbox = diff.getbbox()
     if bbox:
         return image.crop(bbox)
     return image

   