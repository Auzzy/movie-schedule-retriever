import argparse
import base64
import os

from ical.calendar import Calendar
from ical.calendar_stream import IcsCalendarStream
from ical.event import Event
from mailtrap import Address, Attachment, Mail, MailtrapClient

from fandango_json import load_schedules_by_day
from schedule import THEATER_CODE_DICT, Filter, FullSchedule, date_range_str_parser


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

def send_email(theaters_to_schedule, subject):
    sender_name = os.getenv("MAILTRAP_SENDER_NAME", "Test Movie Sender")

    attachments = _plaintext_attachments(theaters_to_schedule) + _ics_attachments(theaters_to_schedule)

    mail = Mail(
        sender=Address(email=os.environ["MAILTRAP_SENDER"], name=sender_name),
        to=[Address(email=os.environ["MAILTRAP_RECEIVER"])],
        subject=subject,
        text="Schedules attached",
        attachments=attachments
    )

    client = MailtrapClient(token=os.environ["MAILTRAP_API_TOKEN"])
    client.send(mail)


def collect_schedules(theater, date_range):
    schedules_by_day = load_schedules_by_day(theater, None, date_range, Filter.empty(), quiet=True)

    if not schedules_by_day:
        print("Could not find any data for the requested date(s).")
        return

    return FullSchedule.create(schedules_by_day)

def main():
    date_range_str = os.getenv("SCHEDULE_RETRIEVER_DATES", "next movie week")
    theaters_str = os.getenv("SCHEDULE_RETRIEVER_THEATERS")

    dates = date_range_str_parser(date_range_str)
    subject = f"Movie Schedules {dates[0].isoformat()}"
    if dates[0] != dates[1]:
        subject += f" to {dates[1].isoformat()}"
    theaters = set(theaters_str.split(";")) if theaters_str else THEATER_CODE_DICT.keys()

    theaters_to_schedule = {theater: collect_schedules(theater, dates) for theater in theaters}
    send_email(theaters_to_schedule, subject)


if __name__ == "__main__":
    main()
