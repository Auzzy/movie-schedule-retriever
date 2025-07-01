import calendar
import itertools
import json
import requests
from datetime import date, timedelta

from schedule import DaySchedule, THEATER_CODE_DICT, THEATER_SLUG_DICT


def _load_schedule(showtimes_json):
    day = date.fromisoformat(showtimes_json["viewModel"]["date"])
    schedule = DaySchedule(day)
    for movie_info in showtimes_json["viewModel"]["movies"]:
        if " " in movie_info["title"]:
            name, year_str = movie_info["title"].rsplit(maxsplit=1)
            if year_str[0] != "(" or year_str[-1] != ")" or not all(c.isdigit() for c in year_str[1:-1]):
                name += f" {year_str}"
        else:
            name = movie_info["title"]

        runtime = movie_info["runtime"]

        movie = schedule.add_raw_movie(name, runtime)

        showtimes_sections = itertools.chain.from_iterable([fmt["amenityGroups"] for fmt in movie_info["variants"]])
        for showtimes_listing in showtimes_sections:
            attributes = [attr["name"] for attr in showtimes_listing["amenities"]]
            raw_showtimes = [showtime["date"] for showtime in showtimes_listing["showtimes"]]
            movie.add_raw_showings(attributes, raw_showtimes, day)

    return schedule

def _retrieve_json(theater, showdate):
    url = f"https://www.fandango.com/napi/theaterMovieShowtimes/{THEATER_CODE_DICT[theater]}?startDate={showdate.isoformat()}"
    headers = {"referer": f"https://www.fandango.com/{THEATER_SLUG_DICT[theater]}/theater-page?format=all&date={showdate.isoformat()}"}
    return requests.get(url, headers=headers).json()


def _showtimes_iter(theater, filepath, showdate, date_range):
    if filepath:
        with open(filepath) as showtimes_file:
            yield json.read(showtimes_file)
    elif showdate:
        yield _retrieve_json(theater, showdate)
    elif date_range:
        current_date, end_date = date_range
        while current_date <= end_date:
            yield _retrieve_json(theater, current_date)
            current_date += timedelta(days=1)


def load_schedules_by_day(theater, filepath, showdate, date_range, filter_params):
    schedules_by_day = []
    print(".", end="", flush=True)
    for showtimes_json in _showtimes_iter(theater, filepath, showdate, date_range):
        schedule = _load_schedule(showtimes_json)
        filtered_schedule = schedule.filter(filter_params)
        schedules_by_day.append(filtered_schedule)
        print(".", end="", flush=True)
    print(end="\n\n")

    return schedules_by_day
