import argparse
import base64
import os

from mailtrap import Address, Attachment, Mail, MailtrapClient

from fandango_json import load_schedules_by_day
from schedule import Filter, FullSchedule, date_range_str


THEATERS = {"AMC Methuen", "AMC Boston Common"}


def send_email(theaters_to_schedule):
    attachments = []
    for theater, schedule in theaters_to_schedule.items():
        attachments.append(
            Attachment(
                content=base64.b64encode(schedule.encode('utf-8')),
                filename=f"{theater}.txt"
            )
        )

    mail = Mail(
        sender=Address(email=os.environ["MAILTRAP_SENDER"], name="Movie Schedules"),
        to=[Address(email=os.environ["MAILTRAP_RECEIVER"])],
        subject="Movie Schedules",
        text="Schedules attached",
        attachments=attachments
    )

    client = MailtrapClient(token=os.environ["MAILTRAP_API_TOKEN"])
    client.send(mail)


def collect_schedules(theater, date_range):
    schedules_by_day = load_schedules_by_day(theater, None, date_range, Filter.empty())

    if not schedules_by_day:
        print("Could not find any data for the requested date(s).")
        return

    schedule_range = FullSchedule.create(schedules_by_day)
    return schedule_range.output(name_only=False, date_only=True)

def main():
    dates = date_range_str("next movie week")
    theaters_to_schedule = {theater: collect_schedules(theater, dates) for theater in THEATERS}
    send_email(theaters_to_schedule)


if __name__ == "__main__":
    main()
