import os
import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime

try:
    import psycopg2
    from psycopg2.pool import SimpleConnectionPool
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.use_postgres = self.db_url and self.db_url.startswith("postgres") and POSTGRES_AVAILABLE
        self.pool = None
        self._init_db()

    def _init_db(self):
        if self.use_postgres:
            self.pool = SimpleConnectionPool(1, 10, self.db_url)
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            user_id BIGINT PRIMARY KEY,
                            first_name TEXT,
                            username TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS schedules (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                            date DATE NOT NULL,
                            day_of_week SMALLINT,
                            start_time TIME,
                            end_time TIME,
                            subject TEXT,
                            subject_code TEXT,
                            class_code TEXT,
                            room TEXT,
                            lecturer TEXT,
                            week_range TEXT,
                            learning_type TEXT,
                            note TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_schedules_user_date ON schedules(user_id, date)")
                    conn.commit()
        else:
            db_path = os.getenv("SQLITE_PATH", "schedule.db")
            with self.get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        first_name TEXT,
                        username TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS schedules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
                        date TEXT NOT NULL,
                        day_of_week INTEGER,
                        start_time TEXT,
                        end_time TEXT,
                        subject TEXT,
                        subject_code TEXT,
                        class_code TEXT,
                        room TEXT,
                        lecturer TEXT,
                        week_range TEXT,
                        learning_type TEXT,
                        note TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_schedules_user_date ON schedules(user_id, date)")
                conn.commit()

    @contextmanager
    def get_conn(self):
        if self.use_postgres:
            conn = self.pool.getconn()
            try:
                yield conn
            finally:
                self.pool.putconn(conn)
        else:
            db_path = os.getenv("SQLITE_PATH", "schedule.db")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def upsert_user(self, user_id: int, first_name: str = "", username: str = ""):
        with self.get_conn() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (user_id, first_name, username, updated_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id) DO UPDATE SET
                            first_name = EXCLUDED.first_name,
                            username = EXCLUDED.username,
                            updated_at = CURRENT_TIMESTAMP
                    """, (user_id, first_name, username))
                    conn.commit()
            else:
                conn.execute("""
                    INSERT INTO users (user_id, first_name, username, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        first_name = excluded.first_name,
                        username = excluded.username,
                        updated_at = CURRENT_TIMESTAMP
                """, (user_id, first_name, username))
                conn.commit()

    def clear_schedule(self, user_id: int):
        with self.get_conn() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM schedules WHERE user_id = %s", (user_id,))
                    conn.commit()
            else:
                conn.execute("DELETE FROM schedules WHERE user_id = ?", (user_id,))
                conn.commit()

    def add_schedule_items(self, user_id: int, items: List[Dict[str, Any]]):
        with self.get_conn() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    for item in items:
                        cur.execute("""
                            INSERT INTO schedules (
                                user_id, date, day_of_week, start_time, end_time,
                                subject, subject_code, class_code, room, lecturer,
                                week_range, learning_type, note
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            user_id,
                            item.get("date"),
                            item.get("day_of_week"),
                            item.get("start_time"),
                            item.get("end_time"),
                            item.get("subject"),
                            item.get("subject_code"),
                            item.get("class_code"),
                            item.get("room"),
                            item.get("lecturer"),
                            item.get("week_range"),
                            item.get("learning_type"),
                            item.get("note")
                        ))
                    conn.commit()
            else:
                for item in items:
                    conn.execute("""
                        INSERT INTO schedules (
                            user_id, date, day_of_week, start_time, end_time,
                            subject, subject_code, class_code, room, lecturer,
                            week_range, learning_type, note
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        item.get("date"),
                        item.get("day_of_week"),
                        item.get("start_time"),
                        item.get("end_time"),
                        item.get("subject"),
                        item.get("subject_code"),
                        item.get("class_code"),
                        item.get("room"),
                        item.get("lecturer"),
                        item.get("week_range"),
                        item.get("learning_type"),
                        item.get("note")
                    ))
                conn.commit()

    def get_schedule(self, user_id: int, date_from: str = None, date_to: str = None) -> List[Dict]:
        with self.get_conn() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    query = "SELECT * FROM schedules WHERE user_id = %s"
                    params = [user_id]
                    if date_from:
                        query += " AND date >= %s"
                        params.append(date_from)
                    if date_to:
                        query += " AND date <= %s"
                        params.append(date_to)
                    query += " ORDER BY date, start_time"
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    return [dict(row) for row in rows]
            else:
                query = "SELECT * FROM schedules WHERE user_id = ?"
                params = [user_id]
                if date_from:
                    query += " AND date >= ?"
                    params.append(date_from)
                if date_to:
                    query += " AND date <= ?"
                    params.append(date_to)
                query += " ORDER BY date, start_time"
                cur = conn.execute(query, params)
                return [dict(row) for row in cur.fetchall()]

    def get_next_class(self, user_id: int) -> Optional[Dict]:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")
        with self.get_conn() as conn:
            if self.use_postgres:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT * FROM schedules 
                        WHERE user_id = %s AND (
                            (date = %s AND start_time > %s) OR date > %s
                        )
                        ORDER BY date, start_time LIMIT 1
                    """, (user_id, today, current_time, today))
                    row = cur.fetchone()
                    return dict(row) if row else None
            else:
                cur = conn.execute("""
                    SELECT * FROM schedules 
                    WHERE user_id = ? AND (
                        (date = ? AND start_time > ?) OR date > ?
                    )
                    ORDER BY date, start_time LIMIT 1
                """, (user_id, today, current_time, today))
                row = cur.fetchone()
                return dict(row) if row else None


db = Database()