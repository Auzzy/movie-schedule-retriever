import os
from datetime import datetime
import sqlite3

import psycopg2
from psycopg2.extras import RealDictCursor


def _connect():
    global _DATE, _PH
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        _PH = "%s"
        _DATE = "::date"
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    else:
        _PH = "?"
        _DATE = ""
        db = sqlite3.connect("showtimes.db")
        db.row_factory = sqlite3.Row
        return db

def load_showtimes(theater, first_date, last_date):
    db = _connect()
    cur = db.cursor()

    cur.execute(f"""
        SELECT *
        FROM showtimes s
        WHERE s.theater = {_PH} AND s.start_date{_DATE} >= {_PH} AND s.start_date{_DATE} <= {_PH}
        ORDER BY s.title""",
        (theater, first_date, last_date)
    )
    return cur.fetchall()

def store_showtimes(theater, schedule):
    db = _connect()
    cur = db.cursor()

    for movie in schedule.movies:
        for showing in movie.showings:
            fields = (
                theater,
                movie.name,
                showing.fmt,
                int(showing.is_open_caption),
                int(not showing.no_alist),
                showing.start.date().isoformat(),
                showing.end.date().isoformat(),
                showing.start.time().isoformat(),
                showing.end.time().isoformat()
            )
            cur.execute(f"""
                INSERT INTO showtimes(theater, title, format, is_open_caption, is_a_list, start_date, end_date, start_time, end_time)
                VALUES ({_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH} )
                ON CONFLICT(theater, title, start_date, start_time) DO NOTHING""",
                fields
            )

    db.commit()
    db.close()

def _init_db():
    db = _connect()
    cur = db.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS showtimes (
        theater TEXT NOT NULL,
        title TEXT NOT NULL,
        format TEXT,
        is_open_caption INT NOT NULL,
        is_a_list INT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        PRIMARY KEY(theater, title, start_date, start_time)
    )""")

    db.commit()
    db.close()


_init_db()
