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

    create_time = datetime.now().isoformat()
    inserted = []
    for movie in schedule.movies:
        for showing in movie.showings:
            field_names = ("theater", "title", "format", "is_open_caption", "is_a_list", "start_date", "end_date", "start_time", "end_time", "create_time")
            field_names_str = ", ".join(field_names)
            field_values = (
                theater,
                movie.name,
                showing.fmt,
                int(showing.is_open_caption),
                int(not showing.no_alist),
                showing.start.date().isoformat(),
                showing.end.date().isoformat(),
                showing.start.time().isoformat(),
                showing.end.time().isoformat(),
                create_time
            )
            inserted.append(dict(zip(field_names, field_values)))
            cur.execute(f"""
                INSERT INTO showtimes({field_names_str})
                VALUES ({_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH})
                ON CONFLICT(theater, title, format, is_open_caption, is_a_list, start_date, start_time) DO NOTHING""",
                field_values
            )

    db.commit()
    db.close()

    return inserted

def delete_showtimes(showtimes_dicts):
    db = _connect()
    cur = db.cursor()

    delete_time = datetime.now().isoformat()
    for showtime in showtimes_dicts:
        delete_field_names = ("theater", "title", "format", "is_open_caption", "is_a_list", "start_date", "start_time")
        delete_field_where_str = " and ".join([f"{field} = {_PH}" for field in delete_field_names])
        delete_field_values = tuple([showtime[field] for field in delete_field_names])
        cur.execute(f"DELETE FROM showtimes WHERE {delete_field_where_str}", delete_field_values)

        insert_field_names = delete_field_names + ("end_date", "end_time", "delete_time")
        insert_field_names_str = ", ".join(insert_field_names)
        insert_field_values = tuple([showtime[field] for field in insert_field_names[:-1]])
        cur.execute(f"""
            INSERT INTO deleted_showtimes(theater, title, format, is_open_caption, is_a_list, start_date, start_time, end_date, end_time, delete_time)
            VALUES ({_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH}, {_PH})""",
            tuple(insert_field_values) + (delete_time,)
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
        create_time TEXT NOT NULL,
        PRIMARY KEY(theater, title, format, is_open_caption, is_a_list, start_date, start_time)
    )""")

    # I could do this as a soft delete from showtimes. But this allows
    # capturing any instance of them re-adding the exact same showtime.
    cur.execute("""CREATE TABLE IF NOT EXISTS deleted_showtimes (
        id BIGSERIAL PRIMARY KEY,
        theater TEXT NOT NULL,
        title TEXT NOT NULL,
        format TEXT,
        is_open_caption INT NOT NULL,
        is_a_list INT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        delete_time TEXT NOT NULL
    )""")

    db.commit()
    db.close()


_init_db()
