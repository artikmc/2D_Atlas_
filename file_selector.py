import tkinter as tk
from tkinter import filedialog, messagebox
import logging
from atlas_loader import load_atlas
from functools import lru_cache
from PIL import Image, ImageEnhance, ImageTk
from image_splitter import ImageSplitter  # Добавьте эту строку в импорты
from language_manager import LanguageManager

class FileSelector:
    def __init__(self, root, current_language):
        self.root = root
        self.current_language = current_language #передаём выбор языка

        self.atlas_image = None  # Изображение атласа
        self.image_grid = None  # Экземпляр ImageGrid
        self.create_widgets()  # Создание виджетов
        self._setup_caching()  # Инициализация кэширования

        self.canvas = tk.Canvas(self.root)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.processed_image = None  # Новая переменная для хранения обработанного изображения
        # Переменные для масштабирования
        self.scale_factor = 1.0
        self.scale_delta = 0.01  # Шаг масштабирования

        self.processed_image_unscaled = None  # Для хранения изображения с эффектами без масштаба
        self.canvas_image_id = None  # Для обновления изображения на canvas

        # Привязка событий мыши
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)  # Масштабирование колесиком мыши
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)  # Нажатие левой кнопки мыши
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)  # Перемещение с зажатой левой кнопкой мыши
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)  # Отпускание левой кнопки мыши


    def create_widgets(self):
        # Кнопка для выбора файла
        self.btn_select_file = tk.Button(self.root, text=LanguageManager.get_text("select_file"), command=self.select_file)
        self.btn_select_file.pack(pady=20)
    
        
        # Кнопка для обработки изображения
        self.btn_image_splitter = tk.Button(self.root, text=LanguageManager.get_text("process_btn"), command=self.open_image_splitter)
        self.btn_image_splitter.pack(pady=10)
        
        # Кнопка для выхода
        self.btn_exit = tk.Button(self.root, text=LanguageManager.get_text("exit_btn"), command=self.root.quit)
        self.btn_exit.pack(pady=10)

    def _setup_caching(self):
        """Инициализация параметров кэширования"""
        self.cache_maxsize = 128  # Максимальное количество кэшированных результатов
        self._last_enhance_params = (1.0, 1.0, 1.0)  # Последние параметры улучшения
    
    @lru_cache(maxsize=128)
    def _apply_enhancements_cached(self, sharpness, contrast, brightness):
        """Кэшированная версия применения улучшений к изображению"""
        if self.atlas_image is None:
            return None
            
        img = self.atlas_image.copy()
        
        if sharpness != 1.0:
            img = ImageEnhance.Sharpness(img).enhance(sharpness)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)
            
        return img
    def clear_cache(self):
        """Очистка кэша (вызывать при загрузке нового изображения)"""
        self._apply_enhancements_cached.cache_clear()
        self._last_enhance_params = (1.0, 1.0, 1.0)


    def select_file(self):
        file_path = filedialog.askopenfilename(
            title=LanguageManager.get_text("select_atlas_file"),
            filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpeg"), ("JPG files", "*.jpg"), ("All files", "*.*")]
        )
        if file_path:
            self.clear_cache()
            if not file_path.lower().endswith((".png", ".jpeg", ".jpg")):
                messagebox.showerror(LanguageManager.get_text("error"), LanguageManager.get_text("file_format_error"))
                return
            
            self.atlas_image = load_atlas(file_path)  # Загрузить изображение

            if self.atlas_image is not None:
                # Создаем Canvas с увеличением и сеткой
                self.create_sliders()  # Создаем ползунки
                self.update_image_display(self.atlas_image)  # Отображаем изображение
                self.processed_image = self.atlas_image.copy()  # Сохраняем копию исходного изображения
            else:
                logging.error("Не удалось загрузить изображение: {}".format(file_path))
                messagebox.showerror(LanguageManager.get_text("error"), "Не удалось загрузить изображение. Проверьте файл.")

    def create_sliders(self):
        """Создает ползунки для управления резкостью, контрастом и яркостью."""
        slider_frame = tk.Frame(self.root)
        slider_frame.pack(padx=10, pady=10)

        # Ползунок для резкости
        self.sharpness_slider = tk.Scale(slider_frame, from_=0, to=2, resolution=0.1,
                                          orient=tk.HORIZONTAL, label=LanguageManager.get_text("sharpness"))
        self.sharpness_slider.set(1.0)
        self.sharpness_slider.pack(fill=tk.X)

        # Ползунок для контраста
        self.contrast_slider = tk.Scale(slider_frame, from_=0, to=2, resolution=0.1,
                                         orient=tk.HORIZONTAL, label=LanguageManager.get_text("contrast"))
        self.contrast_slider.set(1.0)
        self.contrast_slider.pack(fill=tk.X)

        # Ползунок для яркости
        self.brightness_slider = tk.Scale(slider_frame, from_=0, to=2, resolution=0.1,
                                           orient=tk.HORIZONTAL, label=LanguageManager.get_text("brightness"))
        self.brightness_slider.set(1.0)
        self.brightness_slider.pack(fill=tk.X)

        # Кнопка для пикселизации изображения
        #self.btn_pixelate = tk.Button(self.root, text="Пикселизировать", command=self.pixelate_image)
        #self.btn_pixelate.pack(pady=10)

        # Ползунок для управления улучшением изображения
        self.sharpness_slider.bind("<Motion>", lambda event: self.enhance_image())
        self.contrast_slider.bind("<Motion>", lambda event: self.enhance_image())
        self.brightness_slider.bind("<Motion>", lambda event: self.enhance_image())

    def open_image_splitter(self):
        """Обработка изображения и обновление интерфейса."""
        if self.processed_image is None:
            messagebox.showerror(LanguageManager.get_text("error"), LanguageManager.get_text("file_format_error"))
            return
            
        # Применяем текущие настройки улучшения перед передачей
        self.enhance_image()

        # Создаем новое окно для ImageSplitter
        splitter_window = tk.Toplevel(self.root)
        # Сохраняем ссылку на ImageSplitter как атрибут
        self.image_splitter = ImageSplitter(splitter_window, self.processed_image)
    
        # Привязываем обновление изображения в splitter при изменении параметров
        self.sharpness_slider.config(command=lambda _: self.update_splitter_image())
        self.contrast_slider.config(command=lambda _: self.update_splitter_image())
        self.brightness_slider.config(command=lambda _: self.update_splitter_image())

    def update_splitter_image(self):
        """Обновляет изображение в ImageSplitter при изменении параметров"""
        if hasattr(self, 'image_splitter') and self.image_splitter:
            self.enhance_image()  # Сначала применяем изменения к processed_image
            self.image_splitter.update_image(self.processed_image)

    def update_image_display(self, image):
        """Обновляет отображаемое изображение на Canvas."""
        if image is not None:
            self.tk_image = ImageTk.PhotoImage(image)
            self.canvas.delete("all")  # Удаляем старое изображение
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
  

    def pixelate_image(self):
        """Пикселизирует текущее изображение."""
        if self.atlas_image is not None:
            # Параметр определяет степень пикселизации (например, 10 для грубой пикселизации)
            pixel_size = 1
            pixelated_image = self.atlas_image.resize(
                (self.atlas_image.size[0] // pixel_size, self.atlas_image.size[1] // pixel_size),
                Image.NEAREST
            ).resize(
                self.atlas_image.size,
                Image.NEAREST
            )
            self.update_image_display(pixelated_image)  # Обновляем изображение с пикселизацией
        else:
            logging.warning("Изображение не загружено для пикселизации.")


    def enhance_image(self):
        """Улучшает изображение с использованием ползунков."""
        try:
           
            if self.atlas_image is None:
                logging.warning("Изображение не загружено для улучшения.")
                return

            # Получаем текущие значения
            current_params = (
                max(0.0, min(2.0, round(self.sharpness_slider.get(), 2))),  # Ограничение 0-2
                max(0.0, min(2.0, round(self.contrast_slider.get(), 2))),
                max(0.0, min(2.0, round(self.brightness_slider.get(), 2)))
            )

            # Пропускаем обработку если параметры не изменились
            if hasattr(self, '_last_enhance_params') and current_params == self._last_enhance_params:
                return
            
            # Получаем улучшенное изображение
            enhanced_image = self._apply_enhancements_cached(*current_params)

            if enhanced_image:
                 # Сохраняем улучшенное изображение
                self.processed_image = enhanced_image.copy()  # Создаём копию для безопасности
            
                # Применяем текущий масштаб к новому изображению
                if hasattr(self, 'scale_factor') and self.scale_factor != 1.0:
                    self.update_scale(self.processed_image)
                else:
                    self.update_image_display(self.processed_image)
                
                self._last_enhance_params = current_params

                # Если открыт ImageSplitter - обновляем и там
                if hasattr(self, 'image_splitter') and self.image_splitter:
                    self.image_splitter.update_image(self.processed_image)
    
        except Exception as e:
            logging.error("Ошибка при улучшении изображения: {}".format(str(e)))
            messagebox.showerror("Ошибка",  f"Не удалось улучшить изображение: {str(e)}")
            # Сбрасываем кэш при ошибке
            self._apply_enhancements_cached.cache_clear()

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
    # Масштабируем изображение, если оно было обработано, роптк
        if self.processed_image:
            self.update_scale(self.processed_image)

    def update_scale(self, image):
        """Обновляет масштаб изображения и сетки."""
        # Масштабируем изображение
        if image is not None:
            new_width = int(image.width * self.scale_factor)
            new_height = int(image.height * self.scale_factor)
            resized_image = image.resize((new_width, new_height), Image.LANCZOS)

             # Сохраняем оригинал с эффектами (без масштабирования)
            self.processed_image_unscaled = image
        
            # Отображаем масштабированную версию
            self.tk_image = ImageTk.PhotoImage(resized_image)
            self.canvas_image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)

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
        """Рисует выделенную область на Canvas."""
        self.canvas.delete("selection")
        self.canvas.create_rectangle(self.start_x, self.start_y, self.end_x, self.end_y,
                                    outline="red", tags="selection")
    #def update_image(self, new_image):
        #"""Обновляет изображение на Canvas."""
        #self.atlas_image = new_image  # Сохраняем новое изображение
        #self.tk_image = ImageTk.PhotoImage(self.atlas_image)  # Преобразуем в PhotoImage
        #self.itemconfig(self.image_on_canvas, image=self.tk_image)  # Обновляем изображение на Canvas
        #self.update_scale()  # Обновляем масштаб
        #logging.info("Изображение обновлено на Canvas")