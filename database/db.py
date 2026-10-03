import os
import aiosqlite
from datetime import date, datetime
from typing import List, Optional
from pathlib import Path

# На Railway поставь переменную DB_PATH=/data/curator.db (путь внутри Volume)
DB_PATH = Path(os.getenv("DB_PATH", "curator.db"))


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        # Пользователи
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Задачи
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                student_name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                due_date TEXT NOT NULL,
                is_done INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        await db.commit()


async def add_user(user_id: int, full_name: str = None, username: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (user_id, full_name, username, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, full_name, username, datetime.now().isoformat())
        )
        await db.commit()


async def get_all_users() -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def add_task(
    user_id: int,
    student_name: str,
    category: str,
    description: str,
    due_date: date,
    notes: str = None
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO tasks (user_id, student_name, category, description, due_date, created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, student_name, category, description, due_date.isoformat(),
             datetime.now().isoformat(), notes)
        )
        await db.commit()
        return cursor.lastrowid


async def task_exists(user_id: int, student_name: str, description: str, due_date: date) -> bool:
    """Есть ли уже такая задача (в том числе выполненная). Нужно, чтобы импорт .ics не плодил дубли."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT 1 FROM tasks
            WHERE user_id = ? AND student_name = ? AND description = ? AND due_date = ?
            LIMIT 1
            """,
            (user_id, student_name, description, due_date.isoformat())
        )
        return await cursor.fetchone() is not None


async def get_tasks_by_date(user_id: int, target_date: date, only_active: bool = True) -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM tasks WHERE user_id = ? AND due_date = ?"
        if only_active:
            query += " AND is_done = 0"
        query += " ORDER BY category, student_name"

        cursor = await db.execute(query, (user_id, target_date.isoformat()))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_active_tasks(user_id: int) -> List[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND is_done = 0
            ORDER BY due_date, category
            """,
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_tasks_by_student(user_id: int, name: str) -> List[dict]:
    # SQLite LIKE не игнорирует регистр для кириллицы ("иванов" не найдёт "Иванов"),
    # поэтому фильтруем в Python через casefold()
    needle = name.strip().casefold()
    tasks = await get_active_tasks(user_id)
    found = [t for t in tasks if needle in (t["student_name"] or "").casefold()]
    return sorted(found, key=lambda t: t["due_date"])


async def mark_done(user_id: int, task_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE tasks SET is_done = 1 WHERE id = ? AND user_id = ?",
            (task_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_task(user_id: int, task_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_task(user_id: int, task_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def count_calendar_tasks(user_id: int) -> int:
    """Сколько задач создано импортом календаря (включая выполненные и старые 'meeting')."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND category IN ('calendar', 'meeting')",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row[0]


async def delete_calendar_tasks(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM tasks WHERE user_id = ? AND category IN ('calendar', 'meeting')",
            (user_id,)
        )
        await db.commit()
        return cursor.rowcount


async def get_overdue_tasks(user_id: int, before: date) -> List[dict]:
    """Невыполненные задачи, у которых дедлайн раньше указанной даты."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND is_done = 0 AND due_date < ?
            ORDER BY due_date, category
            """,
            (user_id, before.isoformat())
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
