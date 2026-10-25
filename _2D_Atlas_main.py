import tkinter as tk
from atlas_interface import AtlasInterface
from database import initialize_database


def main():
    try:
     # Инициализация базы данных (создание таблиц, если их нет)
        print("Инициализация базы данных...")
        initialize_database()
        print("База данных инициализирована.")

        # Создание главного окна
        root = tk.Tk()
        root.title("Главное меню")

        # Создание интерфейса
        app = AtlasInterface(root)
        print("Интерфейс создан.")


        # Запуск главного цикла
        print("Запуск главного цикла...")
        root.mainloop()

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        # Закрытие программы в случае ошибки
        if "root" in locals():
            root.destroy()


if __name__ == "__main__":
    main()
