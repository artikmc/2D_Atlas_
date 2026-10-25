import tkinter as tk
from PIL import Image, ImageTk, ImageChops
from io import BytesIO
from database import create_connection, insert_frame
from tkinter import filedialog, messagebox
from paint_app import PaintApp

class AnimationViewer(tk.Toplevel):
    def __init__(self, master, last_selected_region, class_name, main_frame_id):
        super().__init__(master)
        self.title(f"Анимация: {class_name}")
        self.class_name = class_name
        
        self.update()  # Обновляем окно для отображения
        self.selected_region = last_selected_region  # Выделенная область
        self.main_frame_id = main_frame_id  # ID основного кадра
        self.frames = []  # Список для хранения кадров
        self.current_frame_index = 0  # Индекс текущего кадра
        self.delay = 200  # Задержка между кадрами (в миллисекундах)
        self.is_animating = False  # Флаг для отслеживания состояния анимации (добавлено)

        # Создаем виджеты
        self.create_widgets()

    def create_widgets(self):      
        # Создаем Canvas для отображения кадров
        self.canvas = tk.Canvas(self, width=self.selected_region.width, height=self.selected_region.height)
        self.canvas.pack()
                
        # Отображаем выделенную область
        self.tk_image = ImageTk.PhotoImage(self.selected_region)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)

        # Слайдер для настройки количества кадров
        self.num_frames_slider = tk.Scale(self, from_=1, to=10, orient=tk.HORIZONTAL, label="Количество кадров")
        self.num_frames_slider.set(4)  # Значение по умолчанию
        self.num_frames_slider.pack(pady=10)

         # Слайдер для изменения скорости анимации
        self.speed_slider = tk.Scale(self, from_=100, to=500, orient=tk.HORIZONTAL, label="Скорость (мс)")
        self.speed_slider.set(200)  # Значение по умолчанию
        self.speed_slider.pack(pady=10)

        # Кнопки для управления
        self.create_buttons()

        # Кнопки для редактирования кадров
        #self.create_edit_buttons()

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
    
    def split_frames(self):
        """Разделяет выделенную область на кадры."""
        width, height = self.selected_region.size
        num_frames = self.num_frames_slider.get()  # Получаем значение слайдера
        frame_width = width // num_frames

        self.frames = []
        for i in range(num_frames):
            left = i * frame_width
            right = (i + 1) * frame_width
            frame = self.selected_region.crop((left, 0, right, height))
            frame = remove_empty_space(frame)  # Удаляем пустоты
            self.frames.append(ImageTk.PhotoImage(frame))

        print(f"Разделено на {num_frames} кадров.")
    

    def show_frame(self, index):
        """Отображает кадр с указанным индексом."""
        if 0 <= index < len(self.frames):
            self.current_frame_index = index
            current_frame = self.frames[self.current_frame_index]
            self.canvas.create_image(0, 0, anchor=tk.NW, image=current_frame)
            self.canvas.image = current_frame  # Сохраняем ссылку, чтобы изображение не удалилос

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
         self.show_frame((self.current_frame_index + 1) % len(self.frames))

    def prev_frame(self):
        """Переключает на предыдущий кадр."""
        self.show_frame((self.current_frame_index - 1) % len(self.frames))

    def save_frames(self):
        """Сохраняет анимацию в базу данных."""
        if not self.frames:
            print("Ошибка: Нет кадров для сохранения.")
            return

        conn = create_connection()
        if conn is not None:
            for frame in self.frames:
                with BytesIO() as output:
                    frame._PhotoImage__photo.write(output, format="PNG")
                    frame_data = output.getvalue()
                # Сохраняем кадр с привязкой к основному кадру
                sql = "INSERT INTO frames (class_name, frame_data, main_frame_id) VALUES (?, ?, ?)"
                cursor = conn.cursor()
                cursor.execute(sql, (self.class_name, frame_data, self.main_frame_id))
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

   