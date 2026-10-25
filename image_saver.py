import os 
from PIL import Image

def save_image_region(image, start_x, start_y, end_x, end_y, output_path):
    """
    Сохраняет выделенную область изображения в формате .png.

    :param image: Изображение (PIL.Image)
    :param start_x: Начальная координата X
    :param start_y: Начальная координата Y
    :param end_x: Конечная координата X
    :param end_y: Конечная координата Y
    :param output_path: Путь для сохранения (должен заканчиваться на .png)
    """
    # Проверяем, что выходной путь заканчивается на .png
    if not output_path.lower().endswith(".png"):
        output_path += ".png"

    # Создаем директорию, если её нет
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    
     # Получаем размеры изображения
    width, height = image.size

   # Проверяем, что координаты не выходят за границы изображения
    start_x = max(0, min(start_x, width - 1))
    start_y = max(0, min(start_y, height - 1))
    end_x = max(0, min(end_x, width - 1))
    end_y = max(0, min(end_y, height - 1))

    # Убедимся, что end_x > start_x и end_y > start_y
    if end_x <= start_x or end_y <= start_y:
        raise ValueError("Некорректные координаты выделения")

    # Вырезаем область
    region = (start_x, start_y, end_x, end_y)
    cropped_image = image.crop(region)

    # Сохраняем изображение в формате .png
    cropped_image.save(output_path, format="PNG")
    print(f"Область сохранена: {output_path}")
