import argparse
import base64
import os

from mailtrap import Address, Attachment, Mail, MailtrapClient

from fandango_json import load_schedules_by_day
from schedule import THEATER_CODE_DICT, Filter, FullSchedule, date_range_str_parser


def send_email(theaters_to_schedule, subject):
    sender_name = os.getenv("MAILTRAP SENDER", "Test Movie Sender")

    attachments = []
    for theater, schedule in theaters_to_schedule.items():
        attachments.append(
            Attachment(
                content=base64.b64encode(schedule.encode('utf-8')),
                filename=f"{theater}.txt"
            )
        )

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

    schedule_range = FullSchedule.create(schedules_by_day)
    return schedule_range.output(name_only=False, date_only=True)

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
