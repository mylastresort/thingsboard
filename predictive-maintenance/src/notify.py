import os
from fastapi import APIRouter, Body, HTTPException
import requests
import datetime
from dotenv import load_dotenv

import os
from fastapi import Body, HTTPException
from src.forecast.forecast import router as forecast_router
from src.db_connector import SessionLocal
from sqlalchemy import text
import requests
import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# Handle PhoneNumberID conversion safely
phone_number_id_str = os.getenv("PhoneNumberID")
try:
    PhoneNumberID = (
        int(phone_number_id_str) if phone_number_id_str and phone_number_id_str.isdigit() else None
    )
except (ValueError, TypeError):
    PhoneNumberID = None
WB_TOKEN = os.getenv("WB_TOKEN")

router = APIRouter(
    prefix="",
    tags=["notify"],
)


def send_notification(phone, body):
    try:
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
        raise HTTPException(status_code=500, detail=f"Could not reach sms provider.\n {e}")


@router.post("/api/notify-new-alarm")
def notify_new_alarm(body=Body(None)):
    session = SessionLocal()
    result = session.execute(text("SELECT email, phone from tb_user"))
    result = result.fetchall()
    phones = [row[1] for row in result if row[1] is not None]
    try:
        for i in phones:
            send_notification(i, body)
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Could not reach sms provider.\n {e}")


@router.post("/api/notify-claim-assignee")
def notify_claim_assignee(body=Body(None)):
    email = body["email"]
    body = body["body"]

    session = SessionLocal()
    result = session.execute(text(f"SELECT email from tb_user where email='{email}'"))
    result = result.fetchone()

    phones = [row[0] for row in result if row[0] is not None]

    try:
        send_notification(phones, body)
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
        result = session.execute(text(f"SELECT phone, email from tb_user where id='{assignee}'"))
        result = result.fetchone()
        phone = result[0]
        email = result[1]
        time_fmt = datetime.datetime.fromtimestamp(alarm_start_ts / 1000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        try:
            if email not in (
                "tenant@thingsboard.org",
                "sysadmin@thingsboard.org",
            ):
                if phone is not None:
                    send_notification(
                        phone,
                        {
                            "severity": alarm_severity,
                            "type": alarm_type,
                            "startTs": alarm_start_ts,
                        },
                    )

        except Exception as e:
            print(f"Error: {e}")
            raise HTTPException(status_code=500, detail=f"Could not reach sms provider.\n {e}")
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=404, detail=f"User was not found.\n {e}")
