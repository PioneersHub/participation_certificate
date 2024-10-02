from pytanis.helpdesk import HelpDeskClient, Recipient, Mail, MailClient
import json
from pathlib import Path
from pydantic import BaseModel
from participation_certificate import conf, logger
import shutil
from participation_certificate.models.attendee import Attendee

helpdesk_client = HelpDeskClient()
helpdesk_client.set_throttling(1, 10)


def message(attendee: Attendee):
    """ Message to be sent to the attendees with the certificate link """
    message_text = f"""
Dear {attendee.first_name},

We are thrilled to enclose your Certificate of Attendance for the recent conference. It’s our pleasure to provide this complimentary certificate to all attendees as a token of our appreciation for your participation.

To ensure the authenticity of your certificate, we’ve included a link within the PDF that allows for easy verification through our website.

Please keep in mind that the certificates are issued based on the information provided during registration, and we are unable to make any changes to the details.

2024 Certificates will be available for downloaded until 31.12.2024. Please ensure that you download it by then:
{conf.certificates_url}{attendee.uuid}.pdf

Thank you for being a part of our event. We hope to see you again at future conferences!

All the best,
{conf.event_full_name} Team"""
    return message_text


class Job(BaseModel):
    attendee: Attendee
    file: Path


def collect_certificates():
    path_to_certificates = conf.path_to_certificates / conf.event_short_name
    # mirror with just the pdfs for upload to a webdirectory
    path_to_certificates4upload = conf.path_to_certificates / f"{conf.event_short_name}_upload"
    path_to_certificates4upload.mkdir(exist_ok=True, parents=True)
    jobs = []
    for directory in path_to_certificates.glob("*"):
        if not directory.is_dir():
            continue
        logger.info(f"Processing {directory.name}")
        jsonf = list(directory.glob("*.json"))[0]
        with open(jsonf, "r") as f:
            data = json.load(f)
            attendee = Attendee(**data)
        # only one pdf-file is expected
        pdf = list(directory.glob("*.pdf"))[0]
        dst = path_to_certificates4upload / f"{attendee.uuid}{pdf.suffix}"
        if not dst.exists():
            shutil.copy(pdf, dst)
        jobs.append(Job(attendee=attendee, file=pdf))
    return jobs


def send_certificates(jobs: list[Job], dry_run=False):
    # Conference Tickets
    mail_client = MailClient()
    for i, job in enumerate(jobs, 1):

        recipients = [
            Recipient(name=job.attendee.full_name, email=job.attendee.email, address_as=job.attendee.first_name)]
        # noinspection PyProtectedMember
        mail = Mail(
            subject=f"Certificate of Attendance: {conf.event_full_name}",
            text=message(attendee=job.attendee),
            team_id=conf.email.team_id,
            recipients=recipients,
            agent_id=helpdesk_client._config.HelpDesk.account,
            status="closed",
        )
        responses, errors = mail_client.send(mail, dry_run=dry_run)
        if errors:
            logger.error(f"Error sending mail to {job.attendee.email}: {errors}")


if __name__ == "__main__":
    collect = collect_certificates()
    send_certificates(
        collect, dry_run=False
    )
