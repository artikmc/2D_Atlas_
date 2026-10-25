import tkinter as tk
from tkinter import simpledialog, messagebox
from database import create_connection, get_all_classes, insert_class
import logging  # Импортируем модуль логирования
from language_manager import LanguageManager

class ClassSelector:
    def __init__(self, master, current_class=None):
        self.master = master
        self.current_class = current_class
        self.standard_classes = ["ходьба", "стояние", "падение", "смерть", "бросок", "бег", "прыжок"]
    
        # Настройка логирования
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(message)s",
            filename="image_splitter.log",
            filemode="w",
        )
        logging.info("Инициализация ImageSplitter")
        
    def get_all_classes(self):
        """Возвращает список всех классов из базы данных."""
        conn = create_connection()
        if conn is not None:
            try:
                classes = get_all_classes(conn)
                # Исключаем класс "основной кадр"
                return [cls for cls in classes if cls != "основной кадр"]
            except Exception as e:
                logging.error(f"Ошибка при получении классов: {e}")
                return []
            finally:
                conn.close()

        return []  # Возвращаем пустой список, если не удалось подключиться
    
    def add_class(self, class_name):
        if class_name:
            logging.warning(f"Класс '{class_name}' уже существует, добавление пропущено.")
            return

        """Добавляет новый класс в базу данных."""
        conn = create_connection()
        if conn is not None:
            try:
                
                if class_name in self.get_all_classes():
                    messagebox.showwarning(
                        LanguageManager.get_text("warning"),
                        LanguageManager.get_text("class_exists").format(class_name)
                    )
                    logging.warning(f"Класс '{class_name}' уже существует, добавление пропущено.")
                    return

                insert_class(conn, class_name)
                conn.commit()
                logging.info(f"Добавлен новый класс: {class_name}")
                messagebox.showinfo(
                    LanguageManager.get_text("success"),
                    LanguageManager.get_text("class_added").format(class_name)
                )
            except Exception as e:
                logging.error(f"Ошибка при добавлении класса '{class_name}': {e}")
                messagebox.showerror(
                    LanguageManager.get_text("error"),
                    str(e)
                )
            finally:
                conn.close()
        else:
            logging.error("Ошибка: Не удалось подключиться к базе данных.")
    def ensure_standard_classes_exist(self):
        """Проверяет, что основные классы существуют в базе данных. Если нет, добавляет их."""
        conn = create_connection()
        if conn is not None:
            try:
                existing_classes = get_all_classes(conn)  # Получаем все классы из базы данных
                logging.info(f"Существующие классы: {existing_classes}") # Логируем текущие классы
                for class_name in self.standard_classes:
                    if class_name not in existing_classes:
                        try:
                            insert_class(conn, class_name)  # Добавляем отсутствующий класс
                            logging.info(f"Добавлен новый класс: {class_name}")
                        except Exception as e:
                            logging.error(f"Ошибка при добавлении класса '{class_name}': {e}")
                    else:
                        logging.info(f"Класс '{class_name}' уже существует, пропускаем добавление.")
                conn.commit()  # Фиксируем изменения в базе данных
            except Exception as e:
                logging.error(f"Ошибка при работе с базой данных: {e}")
            finally:
                conn.close()  # Закрываем соединение
        else:
            logging.error("Ошибка: Не удалось подключиться к базе данных.")

    def select_class(self):
        """Выбор класса для сохранения выделенной области."""
        self.ensure_standard_classes_exist()

        # Получаем список всех классов из базы данных
        existing_classes = self.get_all_classes()
        logging.info(f"Существующие классы для выбора: {existing_classes}") 
        #conn.close()

        # Создаем новое окно для выбора класса
        class_dialog = tk.Toplevel(self.master)
        class_dialog.title(LanguageManager.get_text("select_class"))
        class_dialog.geometry("300x400")
             
        # Фрейм для списка классов
        list_frame = tk.Frame(class_dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
        # Создание Listbox вместо кнопок
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        class_list = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            font=("Arial", 12)
        )
        class_list.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=class_list.yview)

        for class_name in existing_classes:
            class_list.insert(tk.END, class_name)

        # Фрейм для кнопок
        button_frame = tk.Frame(class_dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        # Кнопки с переводами
        tk.Button(
            button_frame,
            text=LanguageManager.get_text("select"),
            command=lambda: self._on_class_selected(class_list, class_dialog),
            width=10
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            button_frame,
            text=LanguageManager.get_text("add_class"),
            command=lambda: self._add_class_dialog(class_list),
            width=10
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            button_frame,
            text=LanguageManager.get_text("delete_class"),
            command=lambda: self._delete_class_dialog(class_list),
            width=10
        ).pack(side=tk.LEFT, padx=5)

        class_dialog.wait_window()
        return self.current_class

    def _on_class_selected(self, class_name, dialog):
        """Обрабатывает выбор класса."""
        self.current_class = class_name
        logging.info(f"Выбран класс: {self.current_class}")
        dialog.destroy()  # Закрываем диалоговое окно
    def delete_class(self, class_name):
        """Удаляет класс из базы данных с проверками."""
        if class_name in self.standard_classes:
            confirm = messagebox.askyesno(
                LanguageManager.get_text("warning"),
                LanguageManager.get_text("delete_standard_class_warning").format(class_name)
            )
            if not confirm:
                return False

        classes = self.get_all_classes()
        if len(classes) <= 1:
            messagebox.showwarning(
                LanguageManager.get_text("warning"),
                LanguageManager.get_text("cannot_delete_last_class")
            )
            return False

        conn = create_connection()
        if conn is not None:
            try:
                delete_class(conn, class_name)
                conn.commit()
                logging.info(f"Класс '{class_name}' удален")
                return True
            except Exception as e:
                logging.error(f"Ошибка при удалении класса: {e}")
                messagebox.showerror(
                    LanguageManager.get_text("error"),
                    str(e)
            )
                return False
            finally:
                conn.close()
        return False


    def _add_class_dialog(self, class_list):
        """Диалог добавления нового класса."""
        new_class = simpledialog.askstring(
            LanguageManager.get_text("add_class"),
            LanguageManager.get_text("enter_class_name")
        )
        if new_class:
            self.add_class(new_class)
            class_list.insert(tk.END, new_class)

    def _delete_class_dialog(self, class_list):
        """Диалог удаления класса."""
        selection = class_list.curselection()
        if not selection:
            messagebox.showwarning(
                LanguageManager.get_text("warning"),
                LanguageManager.get_text("no_class_selected")
            )
            return

        class_name = class_list.get(selection[0])
        if self.delete_class(class_name):
            class_list.delete(selection[0])

    def _on_class_selected(self, class_list, dialog):
        """Обработчик выбора класса."""
        selection = class_list.curselection()
        if selection:
            self.current_class = class_list.get(selection[0])
            logging.info(f"Выбран класс: {self.current_class}")
            dialog.destroy()