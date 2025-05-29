import argparse
import calendar
import itertools
import re
import time as ctime
from bs4 import BeautifulSoup
from datetime import date, datetime, time, timedelta
from playwright.sync_api import sync_playwright

RUNTIME_RE = re.compile(r"(?:(?P<hr>\d) hr)? ?(?:(?P<min>\d\d?) min)?")
LANGUAGE_RE = re.compile("([a-z]+) spoken with ([a-z]+) subtitles")


THEATER_SLUG_DICT = {
    "AMC Methuen": "amc-methuen-20-aaoze",
    "AMC Tyngsboro": "amc-tyngsboro-12-aadxs",
    "AMC Boston Common": "amc-boston-common-19-aapnv",
    "Apple Hooksett": "apple-cinemas-hooksett-imax-aauoc",
    "Apple Merrimack": "apple-cinemas-merrimack-aatgl",
    "Showcase Randolph": "showcase-cinemas-de-lux-randolph-aaeea",
    "O'Neil Epping": "oneil-cinemas-at-brickyard-square-aawvb"
}
WEEKDAYS = [day.lower() for day in calendar.day_name]
WEEKDAY_ABBRS = [abbr.lower() for abbr in calendar.day_abbr]
PIVOT_DAY = WEEKDAYS.index("thursday")


class Filter:
    def __init__(self, earliest_start, latest_start, movies, exclude_movies, fmts, exclude_fmts):
        self.earliest_start = earliest_start
        self.latest_start = latest_start
        self.movies = [m.lower() for m in (movies or [])]
        self.exclude_movies = [m.lower() for m in (exclude_movies or [])]
        self.fmts = fmts
        self.exclude_fmts = exclude_fmts

    def apply_movie_filter(self, name):
        if self.movies:
            return name.lower() in self.movies
        elif self.exclude_movies:
            return name.lower() not in self.exclude_movies
        return True

    def apply_start_filter(self, start):
        if self.earliest_start and start < self.earliest_start:
            return False
        if self.latest_start and start > self.latest_start:
            return False
        return True


class Showing:
    @staticmethod
    def _simplify_format(fmt):
        match fmt.lower():
            case "dolby cinema @ amc": return "Dolby"
            case "reald 3d": return "3D"
            case "acx": return "Apple Cinemas Experience"
            case "laser at amc": return "Standard"
            case value: return fmt

    @staticmethod
    def _parse_showtime(showtime_str):
        showtime_str = showtime_str.replace('p', 'pm').replace('a', 'am')
        return datetime.strptime(showtime_str, "%I:%M%p").time()

    @staticmethod
    def create(attributes, raw_start_time, runtime_min, day):
        fmt = Showing._simplify_format(attributes[0])
        languages = [attr.rsplit(maxsplit=1)[0] for attr in attributes if attr.endswith("Language")]
        is_open_caption = "Open caption" in attributes

        start_time = Showing._parse_showtime(raw_start_time)
        start = datetime.combine(day, start_time)
        end = start + timedelta(minutes=runtime_min)
        return Showing(fmt, languages, is_open_caption, start, end)

    def __init__(self, fmt, languages, is_open_caption, start, end):
        self.fmt = fmt
        self.languages = languages
        self.is_open_caption = is_open_caption
        self.start = start
        self.end = end
    
    def filter(self, filter_params):
        return filter_params.apply_start_filter(self.start.time())

    def output(self, show_date):
        date_str = f"{self.start.strftime('%a %B %d')} " if show_date else ""
        time_fmt = "%H:%M"
        dur_str = f"{self.start.strftime(time_fmt)}"
        if self.start != self.end:
            dur_str += f" - {self.end.strftime(time_fmt)}"

        lang_str = f" ({', '.join(self.languages)})" if self.languages else ""
        open_cap_str = " (Open caption)" if self.is_open_caption else ""

        return f"{date_str}{dur_str} ({self.fmt}){lang_str}{open_cap_str}"


class Movie:
    @staticmethod
    def _parse_runtime(runtime_str):
        re_match = RUNTIME_RE.match(runtime_str)
        hr = re_match.group("hr") or 0
        min = re_match.group("min") or 0
        # hr, min = re_match.groups()
        return int(hr) * 60 + int(min or 0)

    @staticmethod
    def create(name, runtime_str):
        return Movie(name, Movie._parse_runtime(runtime_str))

    def __init__(self, name, runtime_min):
        self.name = name
        self.runtime_min = runtime_min
        self.showtimes = []

    def add_raw_showtimes(self, attributes, raw_times, day):
        for raw_time in raw_times:
            self.showtimes.append(Showing.create(attributes, raw_time, self.runtime_min, day))
    
    def __bool__(self):
        return bool(self.showtimes)

    def filter(self, filter_params):
        new_movie = Movie(self.name, self.runtime_min)

        if not filter_params.apply_movie_filter(self.name):
            return new_movie

        for showtime in self.showtimes:
            if showtime.filter(filter_params):
                new_movie.showtimes.append(showtime)
        return new_movie

    def output(self, name_only, show_date):
        output = self.name
        if not name_only:
            output += '\n' + '\n'.join(showtime.output(show_date) for showtime in sorted(self.showtimes, key=lambda s: s.start))
        return output


class DaySchedule:
    def __init__(self, day):
        self.day = day
        self.movies = []

    def add_raw_movie(self, name, runtime_str):
        new_movie = Movie.create(name, runtime_str)
        self.movies.append(new_movie)
        return new_movie

    def filter(self, filter_params):
        new_schedule = DaySchedule(self.day)
        for movie in self.movies:
            filtered_movie = movie.filter(filter_params)
            if filtered_movie:
                new_schedule.movies.append(filtered_movie)
        return new_schedule

    def output(self, name_only):
        date_str = self.day.strftime('%a, %B %d, %Y')
        seplen = len(date_str) + 2
        output = f"""{'-' * seplen}
 {date_str}
{'-' * seplen}
"""
        output += '\n'.join(movie.output(name_only, show_date=False) for movie in sorted(self.movies, key=lambda m: m.name))
        return output


class FullSchedule:
    @staticmethod
    def create(schedules):
        movies = {movie.name: movie for movie in schedules[0].movies}
        days = [schedules[0].day]
        for schedule in schedules[1:]:
            days.append(schedule.day)
            for movie in schedule.movies:
                if movie.name in movies:
                    movies[movie.name].showtimes.extend(movie.showtimes)
                else:
                    movies[movie.name] = movie

        days = sorted(days)
        return FullSchedule(days[0], days[-1], movies.values())

    def __init__(self, start, end, movies):
        self.start = start
        self.end = end
        self.movies = movies

    def output(self, name_only):
        show_date = self.start != self.end

        start_date_str = self.start.strftime('%a, %B %d, %Y')
        end_date_str = self.end.strftime('%a, %B %d, %Y')
        date_str = start_date_str + (f" - {end_date_str}" if show_date else "")
        seplen = len(date_str) + 2
        output = f"""{'-' * seplen}
 {date_str}
{'-' * seplen}
"""
        output += '\n'.join(movie.output(name_only, show_date=show_date) for movie in sorted(self.movies, key=lambda m: m.name))
        return output



def _get_date(page):
    # TODO: How does it handle when the calendar rolls over? Does it also display the year?
    active_date_button = page.find("button", class_="date-picker__date--selected")
    month_text = active_date_button.find("span", class_="date-picker__date-month").get_text(strip=True)
    day_text = active_date_button.find("span", class_="date-picker__date-day").get_text(strip=True)
    return date(date.today().year, list(calendar.month_abbr).index(month_text), int(day_text))

    date_section = page.find("label", attrs={"aria-label": "Date Filter"})
    date_str = date_section("div")[1].get_text(strip=True)
    return date.fromisoformat(date_section.find("option", string=date_str)["value"])


def _load_schedule(page):
    day = _get_date(page)
    schedule = DaySchedule(day)
    for movie_info in page.find("ul", class_="thtr-mv-list").find_all("li", recursive=False):
        header = movie_info.find("h2", class_="thtr-mv-list__detail-title").get_text(strip=True)
        name = header.rsplit(maxsplit=1)[0]

        rating_and_runtime_str = movie_info.find("li", class_="thtr-mv-list__info-bloc-item").get_text(strip=True)
        runtime_str = rating_and_runtime_str.split(", ")[-1] if "," in rating_and_runtime_str else "0 hr 0 min" 

        movie = schedule.add_raw_movie(name, runtime_str)
        
        showtimes_section = movie_info.find("div", class_="thtr-mv-list__amenity-group-wrap")
        for showtimes_listing in showtimes_section("div", class_="thtr-mv-list__amenity-group"):
            attributes = [attr.get_text(strip=True) for attr in showtimes_listing.find("ul", class_="fd-list-inline").find_all("li")]
            raw_showtimes = [next(showtime.stripped_strings) for showtime in showtimes_listing.find("ol", class_="showtimes-btn-list").find_all("li")]
            movie.add_raw_showtimes(attributes, raw_showtimes, day)

    return schedule

def retrieve_page(showdate):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"https://www.fandango.com/amc-methuen-20-aaoze/theater-page?format=all&date={showdate.isoformat()}")
        content = page.content()
        browser.close()
    return content


def showtimes_text_iter(filepath, showdate, date_range):
    if filepath:
        with open(filepath) as showtimes_file:
            yield showtimes_file.read()
    elif showdate:
        yield retrieve_page(showdate)
    elif date_range:
        current_date, end_date = date_range
        while current_date <= end_date:
            yield retrieve_page(current_date)
            current_date += timedelta(days=1)


def main(filepath, showdate, date_range, name_only, filter_params):
    schedules_by_day = []
    print(".", end="", flush=True)
    for showtimes_text in showtimes_text_iter(filepath, showdate, date_range):
        page = BeautifulSoup(showtimes_text, 'html.parser')
        schedule = _load_schedule(page)
        filtered_schedule = schedule.filter(filter_params)
        schedules_by_day.append(filtered_schedule)
        print(".", end="", flush=True)
    print(end="\n\n")

    schedule_range = FullSchedule.create(schedules_by_day)
    print(schedule_range.output(name_only))


def parse_args():
    def time_str(value):
        if value[-1] in ("p", "a"):
            value = value.replace('p', 'pm').replace('a', 'am')
        time_fmt = "%I:%M%p" if value[-2:] in ("pm", "am") else "%H:%M"
        try:
            return datetime.strptime(value, time_fmt).time()
        except ValueError:
            raise argparse.ArgumentTypeError("Expected time in HH:MM format, optionally with am/pm.")

    def date_str(value):
        value = value.lower()
        today = date.today()
        if value == "today":
            return today
        elif value == "tomorrow":
            return today + timedelta(days=1)
        elif value in WEEKDAYS:
            return today + timedelta(days=(WEEKDAYS.index(value) - today.weekday()) % 7)
        elif value in WEEKDAY_ABBRS:
            return today + timedelta(days=(WEEKDAY_ABBRS.index(value) - today.weekday()) % 7)
        else:
            try:
                return date.fromisoformat(value)
            except ValueError:
                raise argparse.ArgumentTypeError("Expected date in ISO format (YYYY-MM-DD).")

    def date_range_str(value):
        if value.lower() == "movie week":
            start = date.today()
            days_left = 6 if start.weekday() == PIVOT_DAY else ((PIVOT_DAY - start.weekday() - 1) % 7)
            end = start + timedelta(days=days_left)
        elif value.lower() == "next movie week":
            today = date.today()
            days_to_pivot = 7 if today.weekday() == PIVOT_DAY else ((PIVOT_DAY - today.weekday()) % 7)
            start = today + timedelta(days=days_to_pivot)
            end = start + timedelta(days=6)
        else:
            try:
                start = date_str(value[:10])
            except argparse.ArgumentTypeError as exc:
                start_str, end_str = value.split("-")
                start = date_str(start_str.strip())
                end = date_str(end_str.strip())
            else:
                end = date_str(value[10:].split('-', 1)[1].strip())

        return (start, end)


    parser = argparse.ArgumentParser()
    parser.add_argument("--theater", default="AMC Methuen", choices=sorted(THEATER_SLUG_DICT.keys()))
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--filepath")
    input_group.add_argument("--date", type=date_str)
    input_group.add_argument("--date-range", type=date_range_str)
    parser.add_argument("--name-only", action="store_true")
    parser.add_argument("--earliest", "-e", type=time_str)
    parser.add_argument("--latest", "-l", type=time_str)
    parser.add_argument("--movie", "-m", action="append")
    parser.add_argument("--not-movie", action="append")
    parser.add_argument("--format", "-f", action="append")
    parser.add_argument("--not-format", action="append")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    filter_params = Filter(args.earliest, args.latest, args.movie, args.not_movie, args.format, args.not_format)
    main(args.filepath, args.date, args.date_range, args.name_only, filter_params)
