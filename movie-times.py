import argparse
import base64
import os

from ical.calendar import Calendar
from ical.calendar_stream import IcsCalendarStream
from ical.event import Event
from mailtrap import Address, Attachment, Mail, MailtrapClient

from retriever import db
from retriever.fandango_json import load_schedules_by_day
from retriever.schedule import THEATER_SLUG_DICT, Filter, FullSchedule, ParseError, \
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


def _ics_attachments(theaters_to_schedule):
    attachments = []
    for theater, schedule in theaters_to_schedule.items():
        calendar = Calendar()
        for movie in schedule.movies:
            for showing in movie.showings:
                start = showing.start
                end = showing.end or (start + timedelta(minutes=5))
                calendar.events.append(
                    Event(summary=movie.name, start=start, end=end),
                )

        calendar_ics = IcsCalendarStream.calendar_to_ics(calendar).encode('utf-8')
        attachments.append(
            Attachment(
                content=base64.b64encode(calendar_ics),
                filename=f"{theater}.ics"
            )
        )

    return attachments

def _plaintext_attachments(theaters_to_schedule):
    attachments = []
    for theater, schedule in theaters_to_schedule.items():
        schedule_text = schedule.output(name_only=False, date_only=True).encode('utf-8')
        attachments.append(
            Attachment(
                content=base64.b64encode(schedule_text),
                filename=f"{theater}.txt"
            )
        )

    return attachments

def _send_email(theaters_to_schedule, subject, sender, sender_name, receiver):
    attachments = _plaintext_attachments(theaters_to_schedule) + _ics_attachments(theaters_to_schedule)

    mail = Mail(
        sender=Address(email=sender, name=sender_name),
        to=[Address(email=receiver)],
        subject=subject,
        text="Schedules attached",
        attachments=attachments
    )

    client = MailtrapClient(token=os.environ["MAILTRAP_API_TOKEN"])
    client.send(mail)


def _collect_schedule(theater, filepath, date_range, filter_params, quiet):
    schedules_by_day = load_schedules_by_day(theater, filepath, date_range, filter_params, quiet)

    if not schedules_by_day:
        print("Could not find any data for the requested date(s).")
        return

    return FullSchedule.create(schedules_by_day)


def sqlite_main(theater, date_range):
    schedule_range = _collect_schedule(theater, None, date_range, Filter.empty(), False)
    db.store_showtimes(theater, schedule_range)

def email_main(dates, theaters, sender, sender_name, receiver):
    theaters = theaters or THEATER_CODE_DICT.keys()

    subject = f"Movie Schedules {dates[0].isoformat()}"
    if dates[0] != dates[1]:
        subject += f" to {dates[1].isoformat()}"

    theaters_to_schedule = {theater: _collect_schedule(theater, None, dates, Filter.empty(), True) for theater in theaters}
    _send_email(theaters_to_schedule, subject, sender, sender_name, receiver)

def cli_main(theater, filepath, date_range, name_only, date_only, filter_params):
    schedule_range = _collect_schedule(theater, filepath, date_range, filter_params, False)
    
    print(end="\n\n")
    print(schedule_range.output(name_only, date_only))
    print(f"\n- {len(schedule_range)} showtimes")

def main(args):
    if args.output == "cli":
        filter_params = Filter(args.earliest, args.latest, args.movie, args.not_movie, args.format, args.not_format)
        cli_main(args.theater, args.filepath, args.date_range, args.name_only, args.date_only, filter_params)
    elif args.output == "email":
        email_main(args.date_range, args.theaters, args.frm, args.from_name, args.to)
    elif args.output == "sqlite":
        sqlite_main(args.theater, args.date_range)



def parse_args():
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(title="output modes")

    cli_parser = subparsers.add_parser("plaintext", help="Output in plaintext to stdout")
    cli_parser.set_defaults(output="cli")
    cli_parser.add_argument("--theater", default="AMC Methuen", choices=sorted(THEATER_SLUG_DICT.keys()))
    input_group = cli_parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--filepath")
    input_group.add_argument("--date", type=date_range_str_parser, dest="date_range")
    cli_parser.add_argument("--name-only", action="store_true")
    cli_parser.add_argument("--date-only", action="store_true")
    cli_parser.add_argument("--earliest", "-e", type=time_str_parser)
    cli_parser.add_argument("--latest", "-l", type=time_str_parser)
    cli_parser.add_argument("--movie", "-m", action="append")
    cli_parser.add_argument("--not-movie", action="append")
    cli_parser.add_argument("--format", "-f", action="append")
    cli_parser.add_argument("--not-format", action="append")
    
    email_parser = subparsers.add_parser("email", help="Email the result.")
    email_parser.set_defaults(output="email")
    email_parser.add_argument("--date", type=date_range_str_parser, dest="date_range", default="next movie week")
    email_parser.add_argument("--theater", action="append", choices=sorted(THEATER_SLUG_DICT.keys()), dest="theaters")
    email_parser.add_argument("--from", dest="frm")
    email_parser.add_argument("--from-name", default="Test Movie Sender")
    email_parser.add_argument("--to")

    sqlite_parser = subparsers.add_parser("sqlite", help="Output the result to an SQLite3 DB.")
    sqlite_parser.set_defaults(output="sqlite")
    sqlite_parser.add_argument("--theater", default="AMC Methuen", choices=sorted(THEATER_SLUG_DICT.keys()))
    sqlite_parser.add_argument("--date", type=date_range_str_parser, dest="date_range", default="next movie week")

    return parser.parse_args()

if __name__ == "__main__":
    main(parse_args())
