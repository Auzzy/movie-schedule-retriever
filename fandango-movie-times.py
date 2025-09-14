import argparse
import calendar
from datetime import date, datetime, timedelta

from fandango_json import load_schedules_by_day
from schedule import MONTHS, MONTH_ABBRS, PIVOT_DAY, THEATER_SLUG_DICT, \
                     WEEKDAYS, WEEKDAY_ABBRS, Filter, FullSchedule


def main(theater, filepath, showdate, date_range, name_only, date_only, filter_params):
    schedules_by_day = load_schedules_by_day(theater, filepath, showdate, date_range, filter_params)

    print(end="\n\n")

    if not schedules_by_day:
        print("Could not find any data for the requested date(s).")
        return

    schedule_range = FullSchedule.create(schedules_by_day)
    print(schedule_range.output(name_only, date_only))
    print(f"\n- {len(schedule_range)} showtimes")


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
                showdate = date.fromisoformat(value)
            except ValueError:
                raise argparse.ArgumentTypeError("Expected date in ISO format (YYYY-MM-DD).")

            if showdate < today:
                raise argparse.ArgumentTypeError(f"Cannot choose a date in the past: {showdate.isoformat()} < {today.isoformat()}")

            return showdate

    def date_range_str(value):
        def month_range(value):
            today = date.today()
            year = today.year + (0 if today.month <= monthno else 1)
            start_day = today.day if today.month == monthno else 1
            end_day = calendar.monthrange(year, monthno)[1]
            return (date(year=year, month=monthno, day=start_day), date(year=year, month=monthno, day=end_day))

        if value in MONTHS:
            monthno = MONTHS.index(value)
            start, end = month_range(monthno)
        elif value in MONTH_ABBRS:
            monthno = MONTH_ABBRS.index(value)
            start, end = month_range(monthno)
        elif value.lower() == "movie week":
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
                start_str, end_str = value.split("-", 1)
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
    parser.add_argument("--date-only", action="store_true")
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
    main(args.theater, args.filepath, args.date, args.date_range, args.name_only, args.date_only, filter_params)
