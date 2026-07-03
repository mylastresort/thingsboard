import datetime
import json
import sys
import time

import requests
from requests.auth import HTTPBasicAuth

machine_id = "03a88ca0-b63e-11ef-a198-07d41c920fc8"
# machine_id = 'ea6210e0-6610-11ef-9061-853a958a524a'
# machine_id = "120e1d10-469d-11f0-b3d7-d5827fb4609f"
alarm = None
host = "thingsboard"
TwilioSmsFrom = "+xxxxxxxxx"
TwilioAccountSid = "xxxxxxxxxx"
TwilioAccountToken = "xxxxxxxxx"


def send_request(data, token, subroute=""):
    return requests.post(
        f"http://{host}:8080/api/alarm" + subroute,
        headers={
            "X-Authorization": token,
            "Content-Type": "application/json",
            "accept": "application/json",
        },
        data=json.dumps(data),
    )


def clear_alarm(data):
    print(f"Alarm cleared.")
    return send_request(data, "/" + data["id"]["id"] + "/clear")


def create_alarm(token, machine_id, alarm_type, severity="MAJOR"):
    print(f"Alarm created.")
    current_time = time.time() * 1000
    data = {
        "type": alarm_type,
        "originator": {
            "id": machine_id,
            "entityType": "DEVICE",
        },
        "severity": severity,
        "startTs": current_time,
        "endTs": current_time,
    }
    try:
        res = send_request(data, token)
        body = res.json()
        return body
    except Exception as e:
        sys.exit(f"Fatal: {e}")


def update_alarm(data, token, endTs):
    data["endTs"] = endTs
    try:
        res = send_request(data, token)
        body = res.json()
        return body
    except Exception as e:
        sys.exit(f"Fatal: {e}")


def authenticate(username="tenant@thingsboard.org", password="tenant"):
    try:
        res = requests.post(
            f"http://{host}:8080/api/auth/login",
            headers={"accept": "application/json", "Content-Type": "application/json"},
            data=json.dumps({"username": username, "password": password}),
        )
        body = res.json()
        return "Bearer " + body["token"]
    except Exception as e:
        sys.exit(f"Fatal: login failed {e}")


def send_to_sms(phones, alarm_type, alarmStartTs, alarmSeverity):
    time_fmt = datetime.datetime.fromtimestamp(alarmStartTs / 1000).strftime("%Y-%m-%d %H:%M:%S")
    sms_body = f"Alarm Created. {alarmSeverity}.\nType: {alarm_type}\nStarted at: {time_fmt}"
    try:
        for phone in phones:
            print(f"phone = {phone}")
            res = requests.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{TwilioAccountSid}/Messages.json",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={"From": TwilioSmsFrom, "To": phone, "Body": sms_body},
                auth=HTTPBasicAuth(TwilioAccountSid, TwilioAccountToken),
            )
            body = res.json()
            print(f"Twilio Response {res.status_code} - {body}")
    except Exception as e:
        print(f"Error: sending sms failed {e}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(f"Fatal: script must take at least 2 arguments: [DELAY] [PHONE]...")
    token = authenticate()
    sleep_time = int(sys.argv[1])
    time.sleep(sleep_time)
    alarm = create_alarm(token, machine_id=machine_id, alarm_type="pressure threshold")
    # phones = sys.argv[2:]
    # send_to_sms(phones, alarm["type"], alarm["startTs"], alarm["severity"])
    for i in range(1, 15):
        # while True:
        time.sleep(1)
        if alarm is None:
            sys.exit(f"Fatal: alarm value is not set. {alarm}")
        update_alarm(alarm, token, alarm["endTs"] + 1000)

    if alarm is None:
        sys.exit(f"Fatal: alarm value is not set. {alarm}")

    clear_alarm(alarm)
