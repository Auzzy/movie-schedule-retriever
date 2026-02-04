import os
from datetime import datetime, timezone
import sqlite3

import psycopg2
from psycopg2.extras import RealDictCursor


def _connect():
    global _DATETIME, _PH
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        _PH = "%s"
        _DATETIME = "::timestamptz"
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    else:
        _PH = "?"
        _DATETIME = ""
        db = sqlite3.connect("showtimes.db")
        db.row_factory = sqlite3.Row
        return db

def load_showtimes(theater, first_time, last_time):
    db = _connect()
    cur = db.cursor()

    cur.execute(f"""
        SELECT *
        FROM showtimes s
        WHERE s.theater = {_PH} AND s.start_time{_DATETIME} >= {_PH} AND s.start_time{_DATETIME} <= {_PH}
        ORDER BY s.title""",
        (theater, first_time, last_time)
    )

    rows = []
    for row in cur.fetchall():
        row_dict = dict(row)
        row_dict["is_open_caption"] = row["is_open_caption"] == 1
        row_dict["no_alist"] = row["no_alist"] == 1
        rows.append(row_dict)
    return rows

def store_showtimes(theater, schedule):
    db = _connect()
    cur = db.cursor()

    create_time = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    inserted = []
    for movie in schedule.movies:
        for showing in movie.showings:
            field_names = ("theater", "title", "format", "is_open_caption", "no_alist", "start_time", "end_time", "create_time")
            field_names_str = ", ".join(field_names)
            field_values = (
                theater,
                movie.name,
                showing.fmt,
                int(showing.is_open_caption),
                int(showing.no_alist),
                showing.start.isoformat(),
                showing.end.isoformat(),
                create_time
            )
            
            cur.execute(f"""
                INSERT INTO showtimes({field_names_str})
                VALUES ({', '.join([_PH] * len(field_names))})
                ON CONFLICT(theater, title, format, is_open_caption, no_alist, start_time) DO NOTHING""",
                field_values
            )
            
            inserted_dict = dict(zip(field_names, field_values))
            inserted_dict["is_open_caption"] = inserted_dict["is_open_caption"] == 1
            inserted_dict["no_alist"] = inserted_dict["no_alist"] == 1
            inserted.append(inserted_dict)

    db.commit()
    db.close()

    return inserted

def delete_showtimes(showtimes_dicts):
    db = _connect()
    cur = db.cursor()

    delete_time = datetime.now(timezone.utc).isoformat()
    for showtime in showtimes_dicts:
        delete_field_names = ("theater", "title", "format", "is_open_caption", "no_alist", "start_time")
        delete_field_where_str = " and ".join([f"{field} = {_PH}" for field in delete_field_names])
        delete_field_raw_values = tuple([showtime[field] for field in delete_field_names])
        delete_field_values = tuple([int(value) if isinstance(value, bool) else value for value in delete_field_raw_values])
        cur.execute(f"DELETE FROM showtimes WHERE {delete_field_where_str}", delete_field_values)

        new_insert_field_names = ("end_time", "delete_time")
        insert_field_names = delete_field_names + new_insert_field_names
        insert_field_names_str = ", ".join(insert_field_names)
        insert_field_values = delete_field_values + tuple([showtime[field] for field in new_insert_field_names[:-1]])
        cur.execute(f"""
            INSERT INTO deleted_showtimes({insert_field_names_str})
            VALUES ({', '.join([_PH] * len(insert_field_names))})""",
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
        no_alist INT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        create_time TEXT NOT NULL,
        PRIMARY KEY(theater, title, format, is_open_caption, no_alist, start_time)
    )""")

    # I could do this as a soft delete from showtimes. But this allows
    # capturing any instance of them re-adding the exact same showtime.
    cur.execute("""CREATE TABLE IF NOT EXISTS deleted_showtimes (
        id BIGSERIAL PRIMARY KEY,
        theater TEXT NOT NULL,
        title TEXT NOT NULL,
        format TEXT,
        is_open_caption INT NOT NULL,
        no_alist INT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        delete_time TEXT NOT NULL
    )""")

    db.commit()
    db.close()


_init_db()
