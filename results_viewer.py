import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from io import BytesIO
import csv
from database import create_connection, get_all_frames, update_frame_class, delete_frame, get_all_classes
from class_selector import ClassSelector  # Импортируем модуль для выбора классов
from animation_viewer import AnimationViewer  # Импортируем модуль для редактирования


class ResultsViewer:
    def __init__(self, parent):
        """
        Инициализация окна для отображения результатов.

        :param parent: Родительское окно (tk.Tk или tk.Toplevel).
        """
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("Результаты")

        # Фрейм для фильтрации и кнопок
        filter_frame = tk.Frame(self.window)
        filter_frame.pack(fill=tk.X, padx=5, pady=5)

        # Поле ввода для фильтрации
        self.filter_entry = tk.Entry(filter_frame)
        self.filter_entry.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)

        # Кнопка "Фильтровать"
        self.btn_filter = tk.Button(filter_frame, text="Фильтровать", command=self.apply_filter)
        self.btn_filter.pack(side=tk.LEFT, padx=5, pady=5)

        # Кнопка "Экспорт в CSV"
        self.btn_export = tk.Button(filter_frame, text="Экспорт в CSV", command=self.export_to_csv)
        self.btn_export.pack(side=tk.LEFT, padx=5, pady=5)

        # Кнопка "Обновить"
        self.btn_refresh = tk.Button(filter_frame, text="Обновить", command=self.load_data)
        self.btn_refresh.pack(side=tk.LEFT, padx=5, pady=5)

        # Создаем Canvas для отрисовки таблицы
        self.canvas = tk.Canvas(self.window, bg="white")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Добавляем вертикальную и горизонтальную прокрутку
        self.v_scroll = ttk.Scrollbar(self.window, orient=tk.VERTICAL, command=self.canvas.yview)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scroll = ttk.Scrollbar(self.window, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.canvas.bind("<Configure>", self.on_canvas_configure)

        # Фрейм для размещения ячеек таблицы
        self.table_frame = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window((0, 0), window=self.table_frame, anchor=tk.NW)

        # Привязываем события
        self.table_frame.bind("<Button-3>", self.show_context_menu)
        self.table_frame.bind("<Double-1>", self.on_double_click)

        # Загружаем данные из базы данных
        self.load_data()

    def on_canvas_configure(self, event):
        """
        Обновляет область прокрутки Canvas при изменении размера.
        """
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def load_data(self, filter_text=None):
        """
        Загружает данные из базы данных и заполняет таблицу.

        :param filter_text: Текст для фильтрации (по умолчанию None).
        """
        conn = create_connection()
        if conn is not None:
            # Получаем все классы
            classes = get_all_classes(conn)

            # Получаем все кадры из базы данных
            frames = get_all_frames(conn)

            print("Classes:", classes)
            print("Frames:", frames)

            # Фильтрация данных
            if filter_text:
                frames = [frame for frame in frames if filter_text.lower() in frame[1].lower()]

            # Очищаем таблицу перед заполнением
            for widget in self.table_frame.winfo_children():
                widget.destroy()

            self.images = {}

            # Заголовки столбцов
            headers = ["№", "Основной кадр"] + classes
            for col_idx, column in enumerate(headers):
                label = tk.Label(self.table_frame, text=column, borderwidth=1, relief=tk.SOLID, width=15, height=2)
                label.grid(row=0, column=col_idx, sticky="nsew")

            # Группируем кадры по основному кадру
            main_frames = {}
            for frame in frames:
                frame_id, class_name, frame_data = frame
                if class_name == "Основной кадр":
                    main_frames[frame_id] = {
                        "main_frame": frame_data,
                        "classes": {}
                    }
                else:
                    # Находим основной кадр для этого класса
                    main_frame_id = self.get_main_frame_id_for_class(conn, frame_id)
                    if main_frame_id is not None and main_frame_id in main_frames:
                        main_frames[main_frame_id]["classes"][class_name] = frame_data

            # Заполняем таблицу данными
            for row_idx, (main_frame_id, data) in enumerate(main_frames.items()):
                main_frame_data = data["main_frame"]
                classes_data = data["classes"]

                # Номер строки
                label_number = tk.Label(self.table_frame, text=str(row_idx + 1), borderwidth=1, relief=tk.SOLID, width=15, height=2)
                label_number.grid(row=row_idx + 1, column=0, sticky="nsew")

                try:
                    # Основной кадр
                    main_image = Image.open(BytesIO(main_frame_data))
                    main_image.thumbnail((50, 50))
                    main_photo = ImageTk.PhotoImage(main_image)
                    self.images[f"main_{main_frame_id}"] = main_photo

                    label_main = tk.Label(self.table_frame, image=main_photo, borderwidth=1, relief=tk.SOLID)
                    label_main.image = main_photo
                    label_main.grid(row=row_idx + 1, column=1, sticky="nsew")
                except Exception as e:
                    print(f"Ошибка при загрузке основного изображения: {e}")

                # Кадры классов
                for col_idx, cls in enumerate(classes):
                    if cls in classes_data:
                        class_image = Image.open(BytesIO(classes_data[cls]))
                        class_image.thumbnail((50, 50))
                        class_photo = ImageTk.PhotoImage(class_image)
                        self.images[f"class_{main_frame_id}_{cls}"] = class_photo

                        label_class = tk.Label(self.table_frame, image=class_photo, borderwidth=1, relief=tk.SOLID)
                        label_class.image = class_photo
                        label_class.grid(row=row_idx + 1, column=col_idx + 2, sticky="nsew")
                    else:
                        label_empty = tk.Label(self.table_frame, text="", borderwidth=1, relief=tk.SOLID, width=15, height=2)
                        label_empty.grid(row=row_idx + 1, column=col_idx + 2, sticky="nsew")

                # Привязываем события к каждой строке
                for col in range(len(headers)):
                    cell = self.table_frame.grid_slaves(row=row_idx + 1, column=col)[0]
                    cell.bind("<Button-3>", lambda event, row=row_idx: self.show_context_menu(event, row))
                    cell.bind("<Double-1>", lambda event, row=row_idx: self.on_double_click(event, row))
         
            conn.close()  # Закрываем соединение после использования данных

    def apply_filter(self):
        """
        Применяет фильтр к данным таблицы.
        """
        filter_text = self.filter_entry.get()
        self.load_data(filter_text)

    def export_to_csv(self):
        """
        Экспортирует данные таблицы в CSV-файл.
        """
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            try:
                conn = create_connection()
                if conn is not None:
                    with open(file_path, mode="w", newline="", encoding="utf-8") as file:
                        writer = csv.writer(file)
                        # Записываем заголовки
                        headers = ["ID"] + get_all_classes(conn)
                        writer.writerow(headers)
                        # Записываем данные
                        frames = get_all_frames(conn)
                        for frame in frames:
                            frame_id, class_name, _ = frame
                            row = [frame_id] + [class_name if cls == class_name else "" for cls in headers[1:]]
                            writer.writerow(row)
                    conn.close()
                    messagebox.showinfo("Успех", f"Данные экспортированы в {file_path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось экспортировать данные: {e}")

    def show_context_menu(self, event, row):
        """
        Показывает контекстное меню при нажатии правой кнопки мыши на строку таблицы.
        """
        widget = event.widget
        if isinstance(widget, tk.Label):  # Проверяем, что клик был на Label
            clicked_row = widget.grid_info().get("row")
            if clicked_row is not None and clicked_row > 0:  # Игнорируем заголовок таблицы
                self.selected_row = clicked_row - 1
                context_menu = tk.Menu(self.window, tearoff=0)
                context_menu.add_command(label="Удалить", command=self.delete_frame)
                context_menu.add_command(label="Редактировать", command=self.edit_frame)
                context_menu.post(event.x_root, event.y_root)

    def delete_frame(self):
        """
        Удаляет выбранный кадр из базы данных.
        """
        if hasattr(self, "selected_row"):
            frame_id = self.get_frame_id_by_row(self.selected_row)
            if frame_id is not None:
                if messagebox.askyesno("Подтверждение", "Вы уверены, что хотите удалить этот кадр?"):
                    conn = create_connection()
                    if conn is not None:
                       if delete_frame(conn, frame_id):
                        messagebox.showinfo("Успех", "Кадр успешно удален")
                    else:
                        messagebox.showerror("Ошибка", "Не удалось удалить кадр")
                    conn.close()
                    self.load_data()  # Обновляем таблицу

    def edit_frame(self):
        """
        Открывает диалоговое окно для редактирования класса выбранного кадра.
        """
        if hasattr(self, "selected_row"):
            frame_id = self.get_frame_id_by_row(self.selected_row)
            if frame_id is not None:
                conn = create_connection()
                if conn is not None:
                    cursor = conn.cursor()
                    cursor.execute("SELECT frame_data, class_name FROM frames WHERE id = ?", (frame_id,))
                    frame_data, class_name = cursor.fetchone()
                    conn.close()

                    image = Image.open(BytesIO(frame_data))
                    AnimationViewer(self.window, image, class_name)

    def get_frame_id_by_row(self, row):
        """
        Возвращает ID кадра по номеру строки в таблице.
        """
        conn = create_connection()
        if conn is not None:
            frames = get_all_frames(conn)
            conn.close()
            if frames and 0 <= row < len(frames):  # Проверяем, что row в пределах списка
                return frames[row][0]
        return None

    def on_double_click(self, event, row):
        """
        Открывает AnimationViewer для редактирования кадра при двойном клике на строку.
        """
        
        widget = event.widget
        if isinstance(widget, tk.Label):  # Проверяем, что клик был на Label
            row = widget.grid_info().get("row")
            if row is not None and row > 0:  # Игнорируем заголовок таблицы
                frame_id = self.get_frame_id_by_row(row - 1)
                if frame_id is not None:
                    conn = create_connection()
                    if conn is not None:
                        cursor = conn.cursor()
                        cursor.execute("SELECT frame_data, class_name FROM frames WHERE id = ?", (frame_id,))
                        frame_data, class_name = cursor.fetchone()
                        conn.close()

                        image = Image.open(BytesIO(frame_data))
                        AnimationViewer(self.window, image, class_name)
    def get_main_frame_id_for_class(self, conn, frame_id):
        """
        Возвращает ID основного кадра для указанного кадра.

        :param conn: Соединение с базой данных.
        :param frame_id: ID кадра.
        :return: ID основного кадра.
        """
        cursor = conn.cursor()
        cursor.execute("SELECT main_frame_id FROM frame_classes WHERE frame_id = ?", (frame_id,))
        result = cursor.fetchone()
        return result[0] if result else None
   