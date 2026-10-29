# run_clean.py — чистка atlas_database.db от пустых (битых) кадров.
# ЗАПУСК: в PowerShell:  cd G:\...\ваша_папка_проекта  затем  python run_clean.py
# ИЛИ просто двойной клик по файлу, если .py ассоциирован с Python.
import sqlite3

conn = sqlite3.connect("atlas_database.db")
cur = conn.cursor()

total = cur.execute("SELECT COUNT(*) FROM frames").fetchone()[0]
empty = cur.execute("SELECT COUNT(*) FROM frames WHERE length(frame_data)=0").fetchone()[0]
print(f"КАДРОВ ВСЕГО: {total}, из них ПУСТЫХ (битых): {empty}")

if empty:
    cur.execute("DELETE FROM frames WHERE length(frame_data) = 0")
    conn.commit()
    total2 = cur.execute("SELECT COUNT(*) FROM frames").fetchone()[0]
    empty2 = cur.execute("SELECT COUNT(*) FROM frames WHERE length(frame_data)=0").fetchone()[0]
    print(f"ПОСЛЕ ЧИСТКИ: всего {total2}, пустых {empty2}")
else:
    print("ПУСТЫХ КАДРОВ НЕТ — чистить нечего, база цела.")

input("\nНажмите Enter, чтобы закрыть окно...")
