import base64
import os

from ical.calendar import Calendar
from ical.calendar_stream import IcsCalendarStream
from ical.event import Event
from mailtrap import Address, Attachment, Mail, MailtrapClient

from retriever import db
from retriever.fandango_json import load_schedules_by_day
from retriever.schedule import Filter, FullSchedule, ParseError
from retriever.theaters import timezone


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

def send_email(theaters_to_schedule, dates, sender, sender_name, receiver):
    attachments = _plaintext_attachments(theaters_to_schedule) + _ics_attachments(theaters_to_schedule)

    subject = f"Movie Schedules {dates[0].isoformat()}"
    if dates[0] != dates[1]:
        subject += f" to {dates[1].isoformat()}"

    mail = Mail(
        sender=Address(email=sender, name=sender_name),
        to=[Address(email=receiver)],
        subject=subject,
        text="Schedules attached",
        attachments=attachments
    )

    client = MailtrapClient(token=os.environ["MAILTRAP_API_TOKEN"])
    client.send(mail)


def collect_schedule(theater, filepath, date_range, filter_params, quiet):
    schedules_by_day = load_schedules_by_day(theater, filepath, date_range, filter_params, quiet)

    if not schedules_by_day:
        print("[WARN] Could not find any data for the requested date(s).")
        return

    return FullSchedule.create(schedules_by_day)


def db_showtime_updates(theater, date_range, detected_showtimes):
    tz = timezone(theater)
    aware_date_range = (date_range[0].astimezone(tz), date_range[1].astimezone(tz))

    all_showtimes = db.load_showtimes(theater, *aware_date_range)

    for showtime in detected_showtimes:
        del showtime["create_time"]

    deleted_showtimes = []
    for showtime in all_showtimes:
        showtime_dict = dict(showtime)
        del showtime_dict["create_time"]

        if showtime_dict not in detected_showtimes:
            deleted_showtimes.append(showtime_dict)

    db.delete_showtimes(deleted_showtimes)
