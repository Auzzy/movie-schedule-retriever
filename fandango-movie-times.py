import argparse

from fandango_json import load_schedules_by_day
from schedule import THEATER_SLUG_DICT, Filter, FullSchedule, ParseError, \
        date_range_str_parser as _raw_date_parser, time_str_parser as _raw_time_parser


def _wrap_parser(parser):
    def parse(value):
        try:
            return parser(value)
        except ParseError as exc:
            raise argparse.ArgumentTypeError(str(exc))
    return parse

date_range_str_parser = _wrap_parser(_raw_date_parser)
time_str_parser = _wrap_parser(_raw_time_parser)


def main(theater, filepath, date_range, name_only, date_only, filter_params):
    schedules_by_day = load_schedules_by_day(theater, filepath, date_range, filter_params)

    print(end="\n\n")

    if not schedules_by_day:
        print("Could not find any data for the requested date(s).")
        return

    schedule_range = FullSchedule.create(schedules_by_day)
    print(schedule_range.output(name_only, date_only))
    print(f"\n- {len(schedule_range)} showtimes")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--theater", default="AMC Methuen", choices=sorted(THEATER_SLUG_DICT.keys()))
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--filepath")
    input_group.add_argument("--date", type=date_range_str_parser, dest="date_range")
    parser.add_argument("--name-only", action="store_true")
    parser.add_argument("--date-only", action="store_true")
    parser.add_argument("--earliest", "-e", type=time_str_parser)
    parser.add_argument("--latest", "-l", type=time_str_parser)
    parser.add_argument("--movie", "-m", action="append")
    parser.add_argument("--not-movie", action="append")
    parser.add_argument("--format", "-f", action="append")
    parser.add_argument("--not-format", action="append")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    filter_params = Filter(args.earliest, args.latest, args.movie, args.not_movie, args.format, args.not_format)
    main(args.theater, args.filepath, args.date_range, args.name_only, args.date_only, filter_params)
