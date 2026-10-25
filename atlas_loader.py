from PIL import Image
from tkinter import PhotoImage

def load_atlas(file_path):
    """
    Загружает изображение атласа.

    :param file_path: Путь к файлу изображения.
    :return: Объект PIL.Image или None, если загрузка не удалась.
    """
    try:
        # Открываем изображение
        atlas_image = Image.open(file_path)
        # Конвертируем в RGBA (если нужно)
        if atlas_image.mode != "RGBA":
            atlas_image = atlas_image.convert("RGBA")
        return atlas_image
    except Exception as e:
        print(f"Ошибка загрузки изображения: {e}")
        return None