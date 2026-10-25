# theme_engine.py
from tkinter import ttk

class ThemeEngine:
    THEMES = {
        "default": {"bg": "#F0F0F0", "fg": "black", "font": "Arial 10"},
        "cyberpunk": {"bg": "#121212", "fg": "#00FF00", "font": "Courier 10"},
        "anime": {"bg": "#FFF0F5", "fg": "#FF69B4", "font": "Comic Sans MS 10"}
    }
    
    def __init__(self, root):
        self.root = root
        
    def apply_theme(self, theme_name):
        theme = self.THEMES.get(theme_name, self.THEMES["default"])
        self.root.config(bg=theme["bg"])
        # Применяем ко всем виджетам
        for widget in self.root.winfo_children():
            if isinstance(widget, (tk.Label, tk.Button)):
                widget.config(bg=theme["bg"], fg=theme["fg"], font=theme["font"])
