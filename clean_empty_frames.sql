-- ============================================================
-- clean_empty_frames.sql
-- Чистка базы atlas_database.db от «битых» кадров: записей,
-- у которых поле frame_data пустое (0 байт). Такие кадры
-- появились из-за бага сохранения (Tk PhotoImage вместо PIL),
-- и просмотрщик результатов падал на них с UnidentifiedImageError.
--
-- КАК ЗАПУСТИТЬ (Windows):
--   1) Закройте вашу программу (база не должна быть открыта).
--   2) Win+R -> cmd -> cd /d G:\Peton_programma\Rurik_2027\... (папка проекта)
--   3) python -c "import sqlite3; c=sqlite3.connect('atlas_database.db'); c.executescript(open('clean_empty_frames.sql', encoding='utf-8').read()); c.close(); print('Готово')"
--
-- Внутри скрипта каждая команда заканчивается точкой с запятой ;
-- Строки после -- — комментарии, база их игнорирует.
-- ============================================================

-- Показываем, сколько битых кадров найдётся (справочная проверка)
SELECT 'Битых кадров найдено: ' || COUNT(*) FROM frames WHERE length(frame_data) = 0;

-- Удаляем именно их: пустой frame_data
DELETE FROM frames WHERE length(frame_data) = 0;

-- Справку: что осталось в базе по классам
SELECT class_name, COUNT(*) AS количество FROM frames GROUP BY class_name;
