import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from PIL import Image, ImageTk, ImageEnhance
from io import BytesIO
from database import create_connection, insert_frame, get_all_classes
from animation_viewer import AnimationViewer
from class_selector import ClassSelector  # Импортируем ClassSelector
from image_grid import ImageGrid  # Импортируем ImageGrid
import logging  # Импортируем модуль логирования
from language_manager import LanguageManager


class ImageSplitter(tk.Frame):
    def __init__(self, master, processed_image):
        print(f"Изображение передано в ImageSplitter: {type(processed_image)}, размер: {processed_image.
            size if hasattr(processed_image, 'size') else 'N/A'}")
        super().__init__(master)
        self.master = master
           # Улучшенная проверка изображения
        if not isinstance(processed_image, Image.Image):
            raise ValueError(f"Ожидается PIL.Image, получено {type(processed_image)}")
    
        print(f"Изображение передано в ImageSplitter. Размер: {processed_image.size}")

        logging.info(f"Изображение получено. Размер: {processed_image.size}")  # В логи
    
        self.processed_image =  processed_image.copy()  # Сохраняем обработанное изображение
        self.atlas_image = self.processed_image # Для совместимости

        self.grid_enabled = False  # По умолчанию сетка выключена
 
             # Настройка логирования
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(message)s",
            filename="image_splitter.log",
            filemode="w",
        )
        logging.info("Инициализация ImageSplitter")
        
         
        # Проверяем, что atlas_image — это объект PIL.Image
        if not isinstance(processed_image, Image.Image):
            raise ValueError("atlas_image должен быть объектом PIL.Image")
       
        # Главный контейнер
        self.pack(fill=tk.BOTH, expand=True)   

        # Создаем экран (ImageGrid)
        self.image_grid = ImageGrid(self, self.atlas_image)
        self.image_grid.pack(fill=tk.BOTH, expand=True)
        logging.debug("ImageGrid создан и упакован")
        
        # Создаем Canvas и виджеты
        self.canvas = tk.Canvas(self)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Отображаем изображение сразу
        self.tk_image = ImageTk.PhotoImage(self.processed_image)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)    

        # Создаем фрейм для кнопок классов
        self.class_button_frame = tk.Frame(self)  
        self.class_button_frame.pack(fill=tk.X, pady=5)  
       
        # Создаем кнопки для управления
        self.create_buttons()
        logging.debug("Кнопки созданы")
        # Загружаем классы из базы данных
        self.load_classes()
     
    def create_buttons(self):
        
        """Создает кнопки для управления."""
        button_frame = tk.Frame(self)
        button_frame.pack(pady=10)

       # Кнопка для включения/выключения сетки
        self.btn_toggle_grid = tk.Button(
            button_frame,
            text=LanguageManager.get_text("disable_grid" if self.grid_enabled else "enable_grid"),
            command=self.toggle_grid
        )
        self.btn_toggle_grid.pack(side=tk.LEFT, padx=5)

        # Кнопка для применения размера сетки
        self.btn_set_grid_size = tk.Button(
            button_frame, text=LanguageManager.get_text("set_grid_size"), command=self.set_grid_size
        )
        self.btn_set_grid_size.pack(side=tk.LEFT, padx=5)

        # Поле для ввода размера сетки
        self.grid_size_entry = tk.Entry(button_frame)
        self.grid_size_entry.insert(0, "50")  # Значение по умолчанию
        self.grid_size_entry.pack(side=tk.LEFT, padx=5)

        # Кнопка для сохранения основного кадра
        self.btn_save_main_frame = tk.Button(
            button_frame, text=LanguageManager.get_text("main_frame"), command=self.save_main_frame
        )
        self.btn_save_main_frame.pack(side=tk.LEFT, padx=5)

        # Кнопка для выбора класса
        self.btn_select_class = tk.Button(
            button_frame, text=LanguageManager.get_text("select_class"), command=self.select_class
        )
        self.btn_select_class.pack(side=tk.LEFT, padx=5)

         # Кнопка для улучшения изображения
        self.btn_enhance_image = tk.Button(
            button_frame, text=LanguageManager.get_text("enhance_image"), command=self.enhance_image
        )
        self.btn_enhance_image.pack(side=tk.LEFT, padx=5)              
       
        
        # Кнопка для добавления нового класса
        self.btn_add_class = tk.Button(
            button_frame, text=LanguageManager.get_text("add_class"), command=self.add_class
        )
        self.btn_add_class.pack(side=tk.LEFT, padx=5)

        # Кнопка для выхода
        self.btn_exit = tk.Button(button_frame, text=LanguageManager.get_text("exit"), command=self.exit_app)
        self.btn_exit.pack(side=tk.LEFT, padx=5)


    def load_classes(self):
        """Загружает классы из базы данных и создает кнопки для них."""
        conn = create_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM classes")
                classes = cursor.fetchall()

                # Удаляем старые кнопки, если они есть
                for widget in self.class_button_frame.winfo_children():
                    widget.destroy()

                # Создаем кнопку для каждого класса
                for class_row in classes:
                    class_name = class_row[0]
                    btn_class = tk.Button(self.class_button_frame, text=class_name, command=lambda c=class_name: self.set_current_class(c))
                    btn_class.pack(side=tk.LEFT, padx=5, pady=5)

            except Exception as e:
                logging.error(f"Ошибка при загрузке классов: {e}")
                messagebox.showerror("Ошибка", "Не удалось загрузить классы из базы данных.")
            finally:
                conn.close()
        else:
            logging.error("Ошибка: Не удалось подключиться к базе данных")

    def set_current_class(self, class_name):
        """Устанавливает текущий выбранный класс."""
        self.current_class = class_name
        logging.info(f"Выбран класс: {self.current_class}")
        self.open_animation_viewer()


    def update_image(self, new_image):
        """Обновляет изображение в ImageGrid"""
        self.processed_image = new_image
        self.atlas_image = new_image
        self.image_grid.update_image(new_image)
        logging.info("Изображение в ImageSplitter обновлено")


    def add_class(self):
        """Метод для добавления нового класса."""
        new_class = simpledialog.askstring(
             LanguageManager.get_text("add_class"), 
             LanguageManager.get_text("add_class_prompt"))
        if new_class:
            conn = create_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO classes (name) VALUES (?)", (new_class,))
                    conn.commit()
                    messagebox.showinfo(
                        LanguageManager.get_text("success"),
                        LanguageManager.get_text("add_class_success").format(new_class))
                except Exception as e:
                    logging.error(f"Ошибка при добавлении класса: {e}")
                    messagebox.showerror( 
                        LanguageManager.get_text("db_error"),
                        str(e))
                finally:
                    conn.close()
            else:
                logging.error("Ошибка: Не удалось подключиться к базе данных")

 
    def select_class(self):
        """Выбор класса с помощью ClassSelector."""
        class_selector = ClassSelector(self.master)
        selected_class = class_selector.select_class()
        if selected_class:
            self.current_class = selected_class
            logging.info(f"Выбран класс: {self.current_class}")

    def save_main_frame(self):
        """Сохраняет выделенную область как основной кадр."""
        logging.debug("Начало сохранения основного кадра")

        # Получаем координаты выделения из ImageGrid
        self.start_x, self.start_y, self.end_x, self.end_y = self.image_grid.get_selection_coords()

        # Проверяем, что координаты выделения заданы
        if not all([self.start_x, self.start_y, self.end_x, self.end_y]):
            error_msg = LanguageManager.get_text("selection_error")
            logging.error(error_msg)
            messagebox.showerror(LanguageManager.get_text("no_selection"), error_msg)
            return

        # Убедимся, что координаты корректны (end_x > start_x, end_y > start_y)
        x1, x2 = min(self.start_x, self.end_x), max(self.start_x, self.end_x)
        y1, y2 = min(self.start_y, self.end_y), max(self.start_y, self.end_y)

        # Проверяем, что выделение не пустое
        if x2 <= x1 or y2 <= y1:
            error_msg = LanguageManager.get_text("invalid_coords")
            logging.error(error_msg)
            messagebox.showerror(LanguageManager.get_text("no_selection"), error_msg)
            return        

        # Вырезаем область из атласа
        self.main_frame = self.processed_image.crop((x1, y1, x2, y2))
        logging.debug(f"Область вырезана: ({x1}, {y1}) -> ({x2}, {y2})")

        # Сохраняем основной кадр в базу данных
        conn = create_connection()
        if conn is not None:
            try:
                with BytesIO() as output:
                    self.main_frame.save(output, format="PNG")
                    frame_data = output.getvalue()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO frames (class_name, frame_data) VALUES (?, ?)", ("основной кадр", frame_data))
                self.main_frame_id = cursor.lastrowid  # Получаем ID основного кадра
                conn.commit()
                logging.info(f"Основной кадр сохранен в базе данных. ID: {self.main_frame_id}")

            except Exception as e:
                logging.error(f"Ошибка при сохранении основного кадра: {e}")
            finally:
                conn.close()
        else:
            logging.error("Ошибка: Не удалось подключиться к базе данных")
        
        # Очищаем переменную main_frame, чтобы она не использовалась в дальнейшем
        if hasattr(self, "main_frame"):
            del self.main_frame

    def open_animation_viewer(self):
        """Открывает AnimationViewer с выделенной областью."""
            # Вырезаем область из атласа
        if not all([self.start_x, self.start_y, self.end_x, self.end_y]):
            error_msg = LanguageManager.get_text("selection_error")
            logging.error(error_msg)
            messagebox.showerror(LanguageManager.get_text("no_selection"), error_msg)
            return

        # Проверяем, что класс выбран
        if not self.current_class:
            error_msg = LanguageManager.get_text("class_not_selected")
            logging.error(error_msg)
            messagebox.showerror(
                LanguageManager.get_text("error_title"),  # Заголовок окна ошибки
                LanguageManager.get_text("select_class"))    # Сообщение об ошибке
            # Можно добавить кнопку или диалоговое окно для выбора класса
            return
      
        # Вырезаем область из атласа
        x3, x4 = min(self.start_x, self.end_x), max(self.start_x, self.end_x)
        y3, y4 = min(self.start_y, self.end_y), max(self.start_y, self.end_y)

        # Проверяем, что выделение не пустое
        if x4 <= x3 or y4 <= y3:
           error_msg = "Ошибка: Некорректные координаты выделения."
           logging.error(error_msg)
           messagebox.showerror("Ошибка", error_msg)
           return   
        
        selected_region = self.atlas_image.crop((x3, y3, x4, y4))
        logging.debug(f"Область вырезана: ({x3}, {y3}) -> ({x4}, {y4})")
              
        # Проверяем, что координаты выделения заданы
        if not all([self.start_x, self.start_y, self.end_x, self.end_y]):
           error_msg = "Ошибка: Координаты выделения не заданы."
           logging.error(error_msg)
           messagebox.showerror("Ошибка", error_msg)
           return

        # Проверяем, что класс выбран
        if not self.current_class:
            error_msg = "Ошибка: Класс не выбран."
            logging.error(error_msg)
            messagebox.showerror("Ошибка", error_msg)
            return
              
        if not isinstance(selected_region, Image.Image):
           error_msg = "Ошибка: Выделенная область не является изображением."
           logging.error(error_msg)
           messagebox.showerror("Ошибка", error_msg)
           return

        # Открываем AnimationViewer с выделенной областью и выбранным классом добовляеи фигню
        try:
           
            # Сохраняем последнее выделенное изображение
            self.last_selected_region = selected_region

            # Передаем в AnimationViewer
            AnimationViewer(self.master, self.last_selected_region, self.current_class, self.main_frame_id)
            logging.info(f"AnimationViewer открыт для класса '{self.current_class}' с ID основного кадра: {self.main_frame_id}")
        except Exception as e:
            logging.error(f"Ошибка при открытии AnimationViewer: {e}")
            messagebox.showerror("Ошибка", f"Не удалось открыть AnimationViewer: {e}")

    def toggle_grid(self):
        """Включает/выключает сетку."""
                # Переключаем состояние сетки
        self.grid_enabled = not self.grid_enabled

        # Обновляем текст кнопки
        if self.grid_enabled:
            self.btn_toggle_grid.config(text=LanguageManager.get_text("disable_grid"))
        else:
            self.btn_toggle_grid.config(text=LanguageManager.get_text("enable_grid"))

        self.image_grid.toggle_grid()
        logging.info(f"Сетка {'включена' if self.image_grid.grid_enabled else 'выключена'}")

    def set_grid_size(self):
        """Устанавливает размер сетки."""
        try:
            size = int(self.grid_size_entry.get())
            self.image_grid.set_grid_size(size)
            logging.info(f"Размер сетки изменен на {size} пикселей")
        except ValueError:
            error_msg = LanguageManager.get_text("invalid_grid_size")
            logging.error(error_msg)
            messagebox.showerror(LanguageManager.get_text("error"), error_msg)
    def enhance_image(self):
        """Открывает окно для настройки улучшения изображения."""
        from enhance_window import EnhanceWindow  # Ленивый импорт
    
        if not hasattr(self, 'processed_image') or self.processed_image is None:
            messagebox.showerror("Ошибка", "Нет изображения для улучшения")
            return
    
        # Создаем окно улучшения
        enhance_win = tk.Toplevel(self.master)
        EnhanceWindow(
            enhance_win, 
            self.processed_image,
            self.update_enhanced_image  # Callback для обновления
        )

    def update_enhanced_image(self, enhanced_img):
        """Обновляет изображение после улучшения."""
        self.processed_image = enhanced_img
        self.atlas_image = enhanced_img  # Для совместимости
        self.image_grid.update_image(enhanced_img)

    def exit_app(self):
        """Завершает работу приложения."""
        self.master.destroy()
        logging.info("Приложение завершено")
    

