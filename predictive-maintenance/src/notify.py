import os
from fastapi import APIRouter, Body, HTTPException
import requests
import datetime
from requests.auth import HTTPBasicAuth
import smtplib
from dotenv import load_dotenv

import os
from fastapi import FastAPI, Body, HTTPException
from src.forecast.forecast import router as forecast_router
from src.db_connector import SessionLocal
from sqlalchemy import text
import requests
import datetime
import time
from requests.auth import HTTPBasicAuth
import smtplib
from dotenv import load_dotenv
from src.logger import logger  # Global logger
from src.generate_email_alarm_template import create_email_body
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Load environment variables from .env file
load_dotenv()


# Access environment variables
Version = "v22.0"
AccountSid = os.getenv("AccountSid")
logger.info(f"AccountSid {AccountSid}")
AccountToken = os.getenv("AccountToken")
logger.info(f"AccountToken {AccountToken}")
TwilioSmsFrom = os.getenv("TwilioSmsFrom")
logger.info(f"TwilioSmsFrom {TwilioSmsFrom}")
# Handle PhoneNumberID conversion safely
phone_number_id_str = os.getenv("PhoneNumberID")
try:
    PhoneNumberID = (
        int(phone_number_id_str)
        if phone_number_id_str and phone_number_id_str.isdigit()
        else None
    )
except (ValueError, TypeError):
    PhoneNumberID = None
WB_TOKEN = os.getenv("WB_TOKEN")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
APP_PASSWORD = os.getenv("APP_PASSWORD")

router = APIRouter(
    prefix="",
    tags=["notify"],
)

def send_notification(phone, body, sms_body):
    try:
        res = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages.json",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"From": TwilioSmsFrom, "To": phone, "Body": sms_body},
            auth=HTTPBasicAuth(AccountSid, AccountToken),
        )
        bod = res.json()
        print(f"Twilio Response {res.status_code} - {bod}")

        res = requests.post(
            f"https://graph.facebook.com/{Version}/{PhoneNumberID}/messages",
            headers={"Authorization": f"Bearer {WB_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": str(phone),
                "type": "template",
                "template": {
                    "name": "alarms",
                    "language": {"code": "en"},
                    "components": [
                        {
                            "type": "BODY",
                            "parameters": [
                                {
                                    "parameter_name": "severity",
                                    "type": "text",
                                    "text": str(body["severity"]),
                                },
                                {
                                    "parameter_name": "type",
                                    "type": "text",
                                    "text": str(body["type"]),
                                },
                                {
                                    "parameter_name": "start_at",
                                    "type": "text",
                                    "text": str(
                                        datetime.datetime.fromtimestamp(
                                            body["startTs"] / 1000
                                        ).strftime("%Y-%m-%d %H:%M:%S")
                                    ),
                                },
                            ],
                        }
                    ],
                },
            },
        )
        bod = res.json()
        print(f"WB Response {res.status_code} - {bod}")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Could not reach sms provider.\n {e}"
        )


@router.post("/api/notify-new-alarm")
def notify_new_alarm(body=Body(None)):
    session = SessionLocal()
    result = session.execute(text("SELECT email, phone from tb_user"))
    result = result.fetchall()
    emails = [
        row[0]
        for row in result
        if row[0] is not None
        or row[0] in ("tenant@thingsboard.org", "sysadmin@thingsboard.org")
    ]
    email_body = (
        "Subject: New alarm alert.\n\n"
        + f"You got a new alarm alert.\nType: {body['type']}\n"
        + f"Severity: {body['severity']}\n"
        + f"Started at: {datetime.datetime.fromtimestamp(body['startTs'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}"
        + "\n\nAnalyticalBoard."
    )
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, emails, email_body)
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Could not send email.\n {e}")
    phones = [row[1] for row in result if row[1] is not None]
    try:
        for i in phones:
            send_notification(i, body, None)
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(
            status_code=500, detail=f"Could not reach sms provider.\n {e}"
        )


@router.post("/api/notify-claim-assignee")
def notify_claim_assignee(body=Body(None)):
    email = body["email"]
    body = body["body"]

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, email, body)
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Could not send email.\n {e}")


@router.post("/api/notify-alarm-assignee")
def notify_alarm_assignee(body=Body(None)):
    assignee = body["assigneeId"]
    alarm_type = body["type"]
    alarm_severity = body["severity"]
    alarm_start_ts = body["startTs"]

    session = SessionLocal()
    try:
        result = session.execute(
            text(f"SELECT phone, email from tb_user where id='{assignee}'")
        )
        result = result.fetchone()
        phone = result[0]
        email = result[1]
        time_fmt = datetime.datetime.fromtimestamp(alarm_start_ts / 1000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        # body = (
        #     "Subject: New alarm assignment.\n\n"
        #     + f"You got assigned a new alarm alert. {alarm_severity}.\nType: {alarm_type}\nStarted at: {time_fmt}"
        #     + "\n\nAnalyticalBoard."
        # )

        body_text, body_html = create_email_body(alarm_severity, alarm_type, time_fmt)

        try:
            if email is not None and email not in (
                "tenant@thingsboard.org",
                "sysadmin@thingsboard.org",
            ):
                # Create message
                msg = MIMEMultipart('alternative')
                msg['Subject'] = "New Alarm Assignment"
                msg['From'] = EMAIL_ADDRESS
                msg['To'] = email
                
                # Attach both versions
                part1 = MIMEText(body_text, 'plain', 'utf-8')
                part2 = MIMEText(body_html, 'html', 'utf-8')
                msg.attach(part1)
                msg.attach(part2)
                
                # Send email
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(EMAIL_ADDRESS, APP_PASSWORD)
                    server.send_message(msg)  # Use send_message instead of sendmail

            if phone is not None:
                send_notification(
                    phone,
                    {
                        "severity": alarm_severity,
                        "type": alarm_type,
                        "startTs": alarm_start_ts,
                    },
                    body_text
                )

        except Exception as e:
            print(f"Error: {e}")
            raise HTTPException(
                status_code=500, detail=f"Could not reach sms provider.\n {e}"
            )
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=404, detail=f"User was not found.\n {e}")
