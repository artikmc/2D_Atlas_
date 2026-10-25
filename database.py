import sqlite3
from sqlite3 import Error

# Название базы данных
DATABASE_NAME = "atlas_database.db"

def create_connection():
    """
    Создает соединение с базой данных.

    :return: Объект соединения с базой данных.
    """
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        print(f"Соединение с базой данных {DATABASE_NAME} установлено.")
    except Error as e:
        print(f"Ошибка при подключении к базе данных: {e}")
    return conn

def create_tables(conn):
    """
    Создает таблицы в базе данных, если они не существуют.

    :param conn: Объект соединения с базой данных.
    """
    sql_create_frames_table = """
    CREATE TABLE IF NOT EXISTS frames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT NOT NULL,
        frame_data BLOB NOT NULL,
        main_frame_id INTEGER,  -- ID основного кадра
        FOREIGN KEY (main_frame_id) REFERENCES frames(id)
    );
    """
    sql_create_frame_classes_table = """
    CREATE TABLE IF NOT EXISTS frame_classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        frame_id INTEGER NOT NULL,
        main_frame_id INTEGER NOT NULL,
        FOREIGN KEY (frame_id) REFERENCES frames(id),
        FOREIGN KEY (main_frame_id) REFERENCES frames(id)
    );
    """
    sql_create_classes_table = """
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
    """
    sql_create_index_class_name = """
    CREATE INDEX IF NOT EXISTS idx_class_name ON frames (class_name);
    """
    sql_create_index_main_frame_id = """
    CREATE INDEX IF NOT EXISTS idx_main_frame_id ON frames (main_frame_id);
    """

    try:
        cursor = conn.cursor()
        cursor.execute(sql_create_frames_table)
        cursor.execute(sql_create_frame_classes_table)
        cursor.execute(sql_create_classes_table)  # Создаем таблицу classes
        cursor.execute(sql_create_index_class_name)
        cursor.execute(sql_create_index_main_frame_id)
        print("Таблицы созданы или уже существуют.")
        conn.commit()
    except Error as e:
        print(f"Ошибка при создании таблиц: {e}")

def insert_frame(conn, class_name, frame_data):
    """
    Вставляет запись о кадре в базу данных.

    :param conn: Объект соединения с базой данных.
    :param class_name: Название класса (например, "ходьба").
    :param frame_data: Данные кадра (например, бинарные данные изображения).
    """
    if not class_name:
        print("Ошибка: class_name не может быть пустым.")
        return

    if conn is None:
        print("Ошибка: Соединение с базой данных не установлено.")
        return
    
    sql = "INSERT INTO frames (class_name, frame_data) VALUES (?, ?)"
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (class_name, frame_data))
        conn.commit()
        print(f"Кадр класса '{class_name}' успешно добавлен.")
    except Error as e:
        print(f"Ошибка при добавлении кадра: {e}")


def get_frames_by_class(conn, class_name):
    """
    Возвращает все кадры для указанного класса.

    :param conn: Объект соединения с базой данных.
    :param class_name: Название класса.
    :return: Список кадров.
    """
    sql = "SELECT frame_data FROM frames WHERE class_name = ?"
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (class_name,))
        return cursor.fetchall()
    except Error as e:
        print(f"Ошибка при получении кадров: {e}")
        return []


def get_frame_by_id(conn, frame_id):
    """
    Возвращает кадр по его ID.

    :param conn: Объект соединения с базой данных.
    :param frame_id: ID кадра.
    :return: Данные кадра.
    """
    if conn is None:
        print("Ошибка: Соединение с базой данных не установлено.")
        return []

    sql = "SELECT frame_data FROM frames WHERE id = ?"
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (frame_id,))
        return cursor.fetchone()
    except Error as e:
        print(f"Ошибка при получении кадра: {e}")
        return None

def get_all_frames(conn):
    """
    Возвращает все кадры из базы данных.

    :param conn: Объект соединения с базой данных.
    :return: Список всех кадров.
    """
    if conn is None:
        print("Ошибка: Соединение с базой данных не установлено.")
        return []

    sql = "SELECT id, class_name, frame_data FROM frames"
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        return cursor.fetchall()
    except Error as e:
        print(f"Ошибка при получении всех кадров: {e}")
        return []



def update_frame_class(conn, frame_id, new_class_name):
    """
    Обновляет класс для указанного кадра.

    :param conn: Объект соединения с базой данных.
    :param frame_id: ID кадра.
    :param new_class_name: Новый класс.
    """
    if conn is None:
        print("Ошибка: Соединение с базой данных не установлено.")
        return []

    sql = "UPDATE frames SET class_name = ? WHERE id = ?"
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (new_class_name, frame_id))
        conn.commit()
        print(f"Класс кадра {frame_id} изменен на '{new_class_name}'.")
    except Error as e:
        print(f"Ошибка при обновлении кадра: {e}")

def delete_frame(conn, frame_id):
    """
    Удаляет кадр из базы данных.

    :param conn: Объект соединения с базой данных.
    :param frame_id: ID кадра.
    """
    if conn is None:
        print("Ошибка: Соединение с базой данных не установлено.")
        return []

    sql = "DELETE FROM frames WHERE id = ?"
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (frame_id,))
        conn.commit()
        print(f"Кадр {frame_id} удален.")
    except Error as e:
        print(f"Ошибка при удалении кадра: {e}")

def initialize_database():
    """
    Инициализирует базу данных (создает таблицы, если их нет).
    """
    conn = create_connection()
    if conn is not None:
        create_tables(conn)
        conn.close()
    else:
        print("Ошибка: Не удалось установить соединение с базой данных.")
def get_all_classes(conn):
    """
    Возвращает список всех уникальных классов из базы данных.

    :param conn: Объект соединения с базой данных.
    :return: Список уникальных классов.
    """
    if conn is None:
        print("Ошибка: Соединение с базой данных не установлено.")
        return []

    sql = "SELECT DISTINCT class_name FROM frames"
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        classes = [row[0] for row in cursor.fetchall()]
        return classes
    except Error as e:
        print(f"Ошибка при получении классов: {e}")
        return []

def insert_class(conn, class_name):
    """
    Добавляет новый класс в таблицу классов.

    :param conn: Объект соединения с базой данных.
    :param class_name: Название класса.
    """
    if class_name in get_all_classes(conn):
        print(f"Класс '{class_name}' уже существует в базе данных.")
        return

    if conn is None:
        print("Ошибка: Соединение с базой данных не установлено.")
        return

    sql = "INSERT OR IGNORE INTO classes (name) VALUES (?)"
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (class_name,))
        conn.commit()
        if cursor.rowcount > 0:  # Проверяем, был ли добавлен класс
            print(f"Класс '{class_name}' добавлен в базу данных.")
        else:
            print(f"Класс '{class_name}' уже существует в базе данных.")
    except Error as e:
        print(f"Ошибка при добавлении класса: {e}")
