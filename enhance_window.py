import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageEnhance, ImageTk
from language_manager import LanguageManager

class EnhanceWindow(tk.Toplevel):
    def __init__(self, master, image, callback):
        super().__init__(master)
        self.master = master
        self.transient(master)  # Делаем окно модальным
        self.grab_set()  # Захватываем фокус

        self.image = image.copy()
        self.original = image.copy()
        self.callback = callback
        #self.initialized = False  # Добавляем флаг инициализации
       
        self.create_widgets()
       
       # Подписываемся на изменения языка
        LanguageManager.add_observer(self)   
        print(f"Добавлен наблюдатель EnhanceWindow: {self}")  # Отладочный вывод
        #self.initialized = True
                


        self.update_texts()  # Явно вызываем обновление текстов при создании
                # Обработчик закрытия окна
        self.protocol("WM_DELETE_WINDOW", self.on_close)


    def create_widgets(self):
        # Ползунок резкости
        self.sharpness_label = ttk.Label(self)
        self.sharpness_label.pack()
        self.sharpness = ttk.Scale(self, from_=0, to=2, value=1)
        self.sharpness.pack()
        
        # Ползунок контраста
        self.contrast_label = ttk.Label(self)
        self.contrast_label.pack()
        self.contrast = ttk.Scale(self, from_=0, to=2, value=1)
        self.contrast.pack()
        
        # Ползунок яркости
        self.brightness_label = ttk.Label(self)
        self.brightness_label.pack()
        self.brightness = ttk.Scale(self, from_=0, to=2, value=1)
        self.brightness.pack()
        
        # Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        
        self.apply_btn = ttk.Button(btn_frame, command=self.apply_enhance)
        self.apply_btn.pack(side=tk.LEFT, padx=5)
        
        self.cancel_btn = ttk.Button(btn_frame, command=self.destroy)
        self.cancel_btn.pack(side=tk.LEFT)
        
        # Привязка изменений
        self.sharpness.bind("<Motion>", lambda e: self.preview())
        self.contrast.bind("<Motion>", lambda e: self.preview())
        self.brightness.bind("<Motion>", lambda e: self.preview())
    
    def language_changed(self):
        """Вызывается при смене языка"""
        print(f"Language changed to {LanguageManager.get_current_language()}")  # Для отладки
        if hasattr(self, 'sharpness_label'):  # Проверяем, созданы ли виджеты
            self.update_texts()
        
    def update_texts(self):
        """Обновляет все тексты в окне"""
        print(f"Обновление текстов для языка: {LanguageManager.get_current_language()}")
        self.title(LanguageManager.get_text("enhance_window_title"))
        self.sharpness_label.config(text=LanguageManager.get_text("sharpness"))
        self.contrast_label.config(text=LanguageManager.get_text("contrast"))
        self.brightness_label.config(text=LanguageManager.get_text("brightness"))
        self.apply_btn.config(text=LanguageManager.get_text("apply_btn"))
        self.cancel_btn.config(text=LanguageManager.get_text("cancel_btn"))

    def preview(self):
        """Предпросмотр изменений."""
        img = self.original.copy()
        
        # Применяем улучшения
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(self.sharpness.get())
        
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(self.contrast.get())
        
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(self.brightness.get())
        
        self.image = img
        
    def apply_enhance(self):
        """Применяет изменения и закрывает окно."""
        self.callback(self.image)
        self.destroy()


    @classmethod
    def remove_observer(cls, observer):
        if observer in cls._observers:
            cls._observers.remove(observer)
                
    def on_close(self):
        """Обработчик закрытия окна"""
        LanguageManager.remove_observer(self)
        print(f"Удален наблюдатель EnhanceWindow. Осталось: {len(LanguageManager._observers)}")  # Отладка
        self.destroy()


    def __del__(self):
        LanguageManager.remove_observer(self)
        print(f"Удален наблюдатель EnhanceWindow: {self}")  # Отладочный вывод