import calendar
import re
from datetime import datetime, timedelta

RUNTIME_RE = re.compile(r"(?:(?P<hr>\d) hr)? ?(?:(?P<min>\d\d?) min)?")
LANGUAGE_RE = re.compile("([a-z]+) spoken with ([a-z]+) subtitles")


THEATER_CODE_DICT = {
    "AMC Methuen": "aaoze",
    "AMC Tyngsboro": "aadxs",
    "AMC Boston Common": "aapnv",
    "Apple Hooksett": "aauoc",
    "Apple Merrimack": "aatgl",
    "Showcase Randolph": "aaeea",
    "O'Neil Epping": "aawvb"
}
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
        return int(hr) * 60 + int(min or 0)

    @staticmethod
    def create(name, runtime):
        runtime_min = Movie._parse_runtime(runtime) if "hr" in runtime or "min" in runtime else int(runtime)
        return Movie(name, runtime_min)

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

    def add_raw_movie(self, name, runtime):
        new_movie = Movie.create(name, str(runtime))
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
