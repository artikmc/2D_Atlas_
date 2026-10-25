import tkinter as tk
import logging
import os
from file_selector import FileSelector
from PIL import Image, ImageTk
from language_manager import LanguageManager
from enhance_window import EnhanceWindow

class AtlasInterface:
    def __init__(self, root):
        self.root = root
        print("Добавление наблюдателя AtlasInterface")  # Отладочный вывод
        self.initialized = False  # 1. Добавляем флаг инициализации
        
        self.create_widgets()

        LanguageManager.add_observer(self)
        print(f"Текущие наблюдатели: {LanguageManager._observers}")  # Отладочный вывод
        
        # Явно устанавливаем язык при инициализации
        LanguageManager.set_language(LanguageManager.get_current_language()) 

         # Настройка логирования
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(message)s",
            filename="image_splitter.log",
            filemode="w",
        )
        logging.info("Инициализация AtlasInterface")

        self.initialized = True

        self.update_ui_texts()
        
    def create_widgets(self):

        lang_frame = tk.Frame(self.root)
        lang_frame.pack(pady=5)

        flags_path = os.path.join(os.getcwd(), "flags")
        
        self.img_flag_ru = ImageTk.PhotoImage(Image.open(os.path.join(flags_path, "ru_flag.png")).resize((20, 20)))
        self.img_flag_en = ImageTk.PhotoImage(Image.open(os.path.join(flags_path, "en_flag.png")).resize((20, 20)))

        self.btn_lang_ru = tk.Button(lang_frame, image=self.img_flag_ru, text="🇷🇺", 
                                   command=lambda: LanguageManager.set_language("ru"))
        self.btn_lang_ru.pack(side=tk.LEFT, padx=5)
        
        self.btn_lang_en = tk.Button(lang_frame,  image=self.img_flag_en, text="🇺🇸", 
                                   command=lambda: LanguageManager.set_language("en"))
        self.btn_lang_en.pack(side=tk.LEFT, padx=5)
        # Основные кнопки
        self.btn_select_file = tk.Button(self.root, command=self.open_file_selection)
        self.btn_show_results = tk.Button(self.root, command=self.show_results)
        self.btn_ai_module = tk.Button(self.root, command=self.use_ai_module)
        self.btn_settings = tk.Button(self.root, command=self.open_settings)
        self.btn_exit = tk.Button(self.root, command=self.root.quit)
        
        for btn in [self.btn_select_file, self.btn_show_results, 
                   self.btn_ai_module, self.btn_settings, self.btn_exit]:
            btn.pack(pady=10)

    def language_changed(self):
        """Вызывается при смене языка"""
        print("Сработал language_changed в AtlasInterface")
        if self.initialized and hasattr(self, 'btn_select_file'):  # 5. Добавляем проверки
            self.update_ui_texts()

    def open_file_selection(self):
        """Открывает экран выбора файла."""
        self.clear_widgets()  # Очищаем текущие виджеты
        self.file_selector = FileSelector(self.root, LanguageManager.get_current_language())  # Создаем экземпляр FileSelector

    def show_results(self):
        """Показать результаты."""
        from results_viewer import ResultsViewer  # Импортируем класс ResultsViewer
        ResultsViewer(self.root)  # Создаем экземпляр ResultsViewer

    def use_ai_module(self):
        """Работа с модулем ИИ."""
        # Реализуйте функциональность ИИ модуля
        pass

    def clear_widgets(self):
        """Очистить все виджеты на экране."""
        for widget in self.root.winfo_children():
            widget.destroy()
        self.initialized = False  # 7. Сбрасываем флаг при очистке

    def open_settings(self):
        """Открывает окно настроек"""
        #from settings_window import SettingsWindow  # Этот модуль мы создадим позже
        #SettingsWindow(self.root)  # Передаем root для модального окна
   
    def open_enhance_window(self):
        if not hasattr(self, 'current_image'):
            print("Нет изображения для улучшения")
            return
        
        if hasattr(self, '_enhance_window') and self._enhance_window.winfo_exists():
            self._enhance_window.lift()
            return
        
        self._enhance_window = EnhanceWindow(self.root, self.current_image, self.apply_enhancements)
        print(f"Создано окно улучшения. Всего наблюдателей: {len(LanguageManager._observers)}")

    def update_ui_texts(self):
        """Обновляет тексты всех кнопок"""
        if not hasattr(self, 'btn_select_file'):  # 6. Проверяем существование виджетов
            return

        self.root.title(LanguageManager.get_text("app_title"))
        self.btn_select_file.config(text=LanguageManager.get_text("process_btn"))
        self.btn_show_results.config(text=LanguageManager.get_text("results_btn"))
        self.btn_ai_module.config(text=LanguageManager.get_text("ai_btn"))
        self.btn_settings.config(text=LanguageManager.get_text("settings_btn"))
        self.btn_exit.config(text=LanguageManager.get_text("exit_btn"))

# Основной код запуска приложения
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    root = tk.Tk()
    app = AtlasInterface(root)
    root.mainloop()
   