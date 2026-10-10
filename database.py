import sqlite3
from datetime import datetime

DB = "study_plan.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_settings (
        user_id     INTEGER PRIMARY KEY,
        deadline    TEXT,
        study_hours INTEGER DEFAULT 12
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS chapters (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id             INTEGER,
        subject             TEXT,
        chapter_name        TEXT,
        total_classes       INTEGER,
        completed_classes   INTEGER DEFAULT 0,
        class_time_min      INTEGER,
        is_big              INTEGER DEFAULT 0,
        note_done           INTEGER DEFAULT 0,
        practice_done       INTEGER DEFAULT 0,
        revision_done       INTEGER DEFAULT 0,
        exam_ready          INTEGER DEFAULT 0,
        exam_done           INTEGER DEFAULT 0,
        status              TEXT DEFAULT 'pending'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_tasks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER,
        date        TEXT,
        chapter_id  INTEGER,
        task_type   TEXT,
        completed   INTEGER DEFAULT 0,
        carried     INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

def save_deadline(user_id, deadline_str):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''INSERT INTO user_settings(user_id, deadline)
                 VALUES(?,?)
                 ON CONFLICT(user_id) DO UPDATE SET deadline=excluded.deadline''',
              (user_id, deadline_str))
    conn.commit()
    conn.close()

def get_settings(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_chapter(user_id, subject, chapter_name,
                total_classes, class_time_min, is_big):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''INSERT INTO chapters
                 (user_id,subject,chapter_name,total_classes,class_time_min,is_big)
                 VALUES(?,?,?,?,?,?)''',
              (user_id, subject, chapter_name,
               total_classes, class_time_min, is_big))
    conn.commit()
    conn.close()

def get_all_chapters(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM chapters WHERE user_id=? ORDER BY subject,id",
              (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_pending_chapters(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''SELECT * FROM chapters
                 WHERE user_id=? AND status != "done"
                 ORDER BY is_big DESC, id''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def update_chapter_field(chapter_id, field, value):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(f"UPDATE chapters SET {field}=? WHERE id=?",
              (value, chapter_id))
    conn.commit()
    conn.close()

def mark_chapter_done(chapter_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE chapters SET status='done' WHERE id=?", (chapter_id,))
    conn.commit()
    conn.close()

def save_daily_tasks(user_id, date_str, tasks: list):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    for chapter_id, task_type in tasks:
        c.execute('''INSERT INTO daily_tasks
                     (user_id, date, chapter_id, task_type)
                     VALUES(?,?,?,?)''',
                  (user_id, date_str, chapter_id, task_type))
    conn.commit()
    conn.close()

def get_today_tasks(user_id, date_str):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''SELECT dt.id, c.subject, c.chapter_name, dt.task_type, dt.completed
                 FROM daily_tasks dt
                 JOIN chapters c ON c.id = dt.chapter_id
                 WHERE dt.user_id=? AND dt.date=?
                 ORDER BY dt.id''',
              (user_id, date_str))
    rows = c.fetchall()
    conn.close()
    return rows

def complete_task(task_id, chapter_id, task_type):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE daily_tasks SET completed=1 WHERE id=?", (task_id,))
    field_map = {
        "class":    "completed_classes",
        "note":     "note_done",
        "practice": "practice_done",
        "revision": "revision_done",
        "exam":     "exam_done",
    }
    if task_type in field_map:
        if task_type == "class":
            c.execute('''UPDATE chapters
                         SET completed_classes = completed_classes + 1
                         WHERE id=?''', (chapter_id,))
        else:
            c.execute(f"UPDATE chapters SET {field_map[task_type]}=1 WHERE id=?",
                      (chapter_id,))
    conn.commit()
    c.execute('''SELECT practice_done, completed_classes, total_classes
                 FROM chapters WHERE id=?''', (chapter_id,))
    row = c.fetchone()
    if row and row[0] == 1 and row[1] >= row[2]:
        c.execute("UPDATE chapters SET exam_ready=1 WHERE id=?", (chapter_id,))
        conn.commit()
    conn.close()

def carry_incomplete_tasks(user_id, old_date, new_date):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''SELECT chapter_id, task_type FROM daily_tasks
                 WHERE user_id=? AND date=? AND completed=0''',
              (user_id, old_date))
    rows = c.fetchall()
    for r in rows:
        c.execute('''INSERT INTO daily_tasks
                     (user_id, date, chapter_id, task_type, carried)
                     VALUES(?,?,?,?,1)''',
                  (user_id, new_date, r[0], r[1]))
        c.execute('''UPDATE daily_tasks SET carried=1
                     WHERE user_id=? AND date=? AND chapter_id=? AND task_type=?''',
                  (user_id, old_date, r[0], r[1]))
    conn.commit()
    conn.close()
    return len(rows)

def get_progress(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM chapters WHERE user_id=?", (user_id,))
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chapters WHERE user_id=? AND status='done'",
              (user_id,))
    done = c.fetchone()[0]
    conn.close()
    return total, done

def get_today_progress(user_id, date_str):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM daily_tasks WHERE user_id=? AND date=?",
              (user_id, date_str))
    total = c.fetchone()[0]
    c.execute('''SELECT COUNT(*) FROM daily_tasks
                 WHERE user_id=? AND date=? AND completed=1''',
              (user_id, date_str))
    done = c.fetchone()[0]
    conn.close()
    return total, done
