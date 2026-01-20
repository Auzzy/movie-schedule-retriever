from datetime import datetime
import sqlite3

_DB_FILENAME = "showtimes.db"

def load_showtimes(theater, first_date, last_date):
    db = sqlite3.connect(_DB_FILENAME)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    cur.execute("""
        SELECT *
        FROM showtimes s
        WHERE s.theater = ? AND s.startDate >= ? AND s.startDate <= ?
        ORDER BY s.title""",
    [theater, first_date, last_date])
    return cur.fetchall()

def store_showtimes(theater, schedule):
    db = sqlite3.connect(_DB_FILENAME)
    cur = db.cursor()

    for movie in schedule.movies:
        for showing in movie.showings:
            fields = {
                "theater": theater,
                "title": movie.name,
                "format": showing.fmt,
                "isOpenCaption": showing.is_open_caption,
                "isAList": not showing.no_alist,
                "startDate": showing.start.date().isoformat(),
                "startTime": showing.start.time().isoformat(),
                "endDate": showing.end.date().isoformat(),
                "endTime": showing.end.time().isoformat(),
            }
            cur.execute(
                "INSERT OR IGNORE INTO showtimes(theater, title, format, isOpenCaption, isAList, startDate, endDate, startTime, endTime) VALUES (:theater, :title, :format, :isOpenCaption, :isAList, :startDate, :endDate, :startTime, :endTime)",
                fields
            )

    db.commit()

def _init_db():
    db = sqlite3.connect(_DB_FILENAME)
    cur = db.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS showtimes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        theater TEXT NOT NULL,
        title TEXT NOT NULL,
        format TEXT,
        isOpenCaption INT NOT NULL,
        isAList INT NOT NULL,
        startDate TEXT NOT NULL,
        endDate TEXT NOT NULL,
        startTime TEXT NOT NULL,
        endTime TEXT NOT NULL,
        UNIQUE(theater, title, startDate, startTime)
    )""")


_init_db()
