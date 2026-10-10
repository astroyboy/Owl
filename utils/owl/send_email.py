import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path


SMTP_SERVER = "smtp.163.com"
SMTP_PORT = 465

SENDER_EMAIL = "tomara2002@163.com"
SENDER_NAME = "Owl Test Framework"
RECIPIENT_EMAIL = "sunts2@lenovo.com"


def send_report_email(report_path: str | Path) -> None:
    report_path = Path(report_path)

    if not report_path.is_file():
        raise FileNotFoundError(
            f"HTML report does not exist: {report_path}"
        )

    auth_code = os.environ.get("163_SMTP_AUTH_CODE")
    if not auth_code:
        raise RuntimeError(
            "Environment variable 163_SMTP_AUTH_CODE is not set."
        )

    message = EmailMessage()
    message["From"] = formataddr((SENDER_NAME, SENDER_EMAIL))
    message["To"] = RECIPIENT_EMAIL
    message["Subject"] = "Owl Automated Test Report"

    message.set_content(
        "Hello,\n\n"
        "The Owl automated test run has finished.\n"
        "Please find the HTML test report attached.\n\n"
        "Best regards,\n"
        "Owl Test Framework"
    )

    message.add_attachment(
        report_path.read_bytes(),
        maintype="text",
        subtype="html",
        filename=report_path.name,
    )

    with smtplib.SMTP_SSL(
        SMTP_SERVER,
        SMTP_PORT,
        context=ssl.create_default_context(),
        timeout=30,
    ) as server:
        server.login(SENDER_EMAIL, auth_code)
        server.send_message(message)

    print(f"[Owl] Report emailed to {RECIPIENT_EMAIL}")
