# language_manager.py
class LanguageManager:
    _instance = None
    _current_language = "ru"
    _observers = []
    
    translations = {
        "ru": {
            # Главное окно
            "app_title": "Обработка Атласа",
            "process_btn": "Обработка 2D атласа",
            "results_btn": "Показать результаты",
            "ai_btn": "Модуль ИИ",
            "settings_btn": "⚙ Настройки",
            "exit_btn": "Выход",
            
            # Выбор файла
            "select_file": "Выберите файл атласа",
            "load_btn": "Загрузить",
            "select_atlas_file": "Выберите файл атласа",
            "error": "Ошибка",
            "file_format_error": "Файл должен быть в формате .png или .jpeg или .jpg",

            # Перевод ползунков
            "brightness": "Яркость",
            "contrast": "Контраст",
            "sharpness": "Резкость",
            "enhance_window_title": "Улучшение изображения",
            "apply_btn": "Применить",
            "cancel_btn": "Отмена",

             # Новые переводы для ImageSplitter
            "enable_grid": "Включить сетку",
            "disable_grid": "Отключить сетку",
            "set_grid_size": "Применить размер сетки",
            "main_frame": "Основной кадр",
            "select_class": "Выбрать класс",
            "enhance_image": "Улучшить изображение",
            "add_class": "Добавить класс",
            "exit": "Выход",
            "grid_size_prompt": "Введите размер сетки:",
            "add_class_prompt": "Введите имя класса:",
            "add_class_success": "Класс '{}' успешно добавлен",
            "selection_error": "Ошибка выделения",
            "no_selection": "Не выделена область",
            "class_not_selected": "Класс не выбран",
            "invalid_coords": "Ошибка: Некорректные координаты выделения",
            "invalid_grid_size": "Размер сетки должен быть числом",
            "db_error": "Ошибка базы данных",
            "error_title": "Ошибка",
            "select_class": "Пожалуйста, выберите класс перед открытием анимации.",

            #работа с классами
            "select_class": "Выбор класса",
            "add_class": "Добавить класс",
            "delete_class": "Удалить класс",
            "select": "Выбрать",
            "enter_class_name": "Введите название класса:",
            "class_exists": "Класс '{}' уже существует",
            "class_added": "Класс '{}' успешно добавлен",
            "delete_standard_class_warning": "Вы пытаетесь удалить стандартный класс '{}'. Продолжить?",
            "cannot_delete_last_class": "Нельзя удалить последний оставшийся класс",
            "no_class_selected": "Не выбран класс для удаления",
            "warning": "Предупреждение",
            "success": "Успех"
        },
        "en": {
            "app_title": "Atlas Processing",
            "process_btn": "Process 2D Atlas",
            "results_btn": "Show Results",
            "ai_btn": "AI Module",
            "settings_btn": "⚙ Settings",
            "exit_btn": "Exit",
            
            "select_file": "Select Atlas File",
            "load_btn": "Load",
            "select_atlas_file": "Select atlas file",
            "error": "error",
            "file_format_error": "File must be in .png, .jpeg, or .jpg format",

            "brightness": "Brightness",
            "contrast": "Contrast",
            "sharpness": "Sharpness",
            "enhance_window_title": "Image Enhancement",
            "apply_btn": "Apply",
            "cancel_btn": "Cancel",

             # New translations for ImageSplitter
            "enable_grid": "Enable grid",
            "disable_grid": "Disable grid",
            "set_grid_size": "Set grid size",
            "main_frame": "Main frame",
            "select_class": "Select class",
            "enhance_image": "Enhance image",
            "add_class": "Add class",
            "exit": "Exit",
            "grid_size_prompt": "Enter grid size:",
            "add_class_prompt": "Enter class name:",
            "add_class_success": "Class '{}' added successfully",
            "selection_error": "Selection error",
            "no_selection": "No area selected",
            "class_not_selected": "Class not selected",
            "invalid_coords": "Error: Incorrect selection coordinates",
            "invalid_grid_size": "Grid size must be a number",
            "db_error": "Database error",
            "error_title": "Error",
            "select_class": "Incorrect selection coordinates.",

            #работа с классами
            "select_class": "Select Class",
            "add_class": "Add Class",
            "delete_class": "Delete Class",
            "select": "Select",
            "enter_class_name": "Enter class name:",
            "class_exists": "Class '{}' already exists",
            "class_added": "Class '{}' added successfully",
            "delete_standard_class_warning": "You are trying to delete standard class '{}'. Continue?",
            "cannot_delete_last_class": "Cannot delete the last remaining class",
            "no_class_selected": "No class selected for deletion",
            "warning": "Warning",
            "success": "Success"
        }
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def set_language(cls, lang_code):
        if lang_code not in cls.translations:
            raise ValueError(f"Неизвестный код языка: {lang_code}")
        cls._current_language = lang_code
        print(f"Установлен язык: {lang_code}")  # Отладочный вывод
        cls._notify_observers()

    @classmethod
    def get_current_language(cls):
        return cls._current_language

    @classmethod
    def get_text(cls, key):
        return cls.translations[cls._current_language].get(key, f"[{key}]")
        text = cls.translations[cls._current_language].get(key, f"[{key}]")
        print(f"Запрос перевода: {key} -> {text} (язык: {cls._current_language})")
        return text

    @classmethod
    def add_observer(cls, observer):
        if observer not in cls._observers:
            cls._observers.append(observer)
            print(f"Добавлен наблюдатель: {observer}. Всего: {len(cls._observers)}")


    @classmethod
    def _notify_observers(cls):
        print(f"Уведомление наблюдателей о смене языка. Всего наблюдателей: {len(cls._observers)}")  # Отладочный вывод
        for i, observer in enumerate(cls._observers):
            print(f"  Наблюдатель #{i+1}: {observer}")
            observer.language_changed()

    @classmethod
    def remove_observer(cls, observer):
        if observer in cls._observers:
            cls._observers.remove(observer)
            print(f"Удален наблюдатель: {observer}. Осталось: {len(cls._observers)}")