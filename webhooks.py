from fastapi import APIRouter, Request, Header, HTTPException
from typing import Optional
import os

ZOOM_WEBHOOK_SECRET_TOKEN = os.environ.get("ZOOM_WEBHOOK_SECRET_TOKEN")
ZOOM_WEBHOOK_VERIFICATION_TOKEN = os.environ.get("ZOOM_WEBHOOK_VERIFICATION_TOKEN")

router = APIRouter()

@router.post("/webhook")
async def zoom_webhook(request: Request,
                       x_zoom_signature: str = Header(None, alias="x-zoom-signature"),
                       x_zoom_request_timestamp: str = Header(None, alias="x-zoom-request-timestamp")):
    """
    Handles Zoom webhooks for meeting.started and meeting.participant_joined events.
    """
    if not ZOOM_WEBHOOK_VERIFICATION_TOKEN:
        raise HTTPException(status_code=500, detail="ZOOM_WEBHOOK_VERIFICATION_TOKEN not configured")

    if not ZOOM_WEBHOOK_SECRET_TOKEN:
        raise HTTPException(status_code=500, detail="ZOOM_WEBHOOK_SECRET_TOKEN not configured")

    try:
        data = await request.json()
        print(f"Received webhook data: {data}")
        event_type = data.get("event")

        if event_type == "meeting.started":
            meeting_id = data["payload"]["object"]["id"]
            topic = data["payload"]["object"]["topic"]
            start_time = data["payload"]["object"]["start_time"]
            print(f"Meeting Started: ID={meeting_id}, Topic='{topic}', Start Time={start_time}")

        elif event_type == "meeting.participant_joined":
            participant_name = data["payload"]["object"]["participant"]["user_name"]
            meeting_id = data["payload"]["object"]["id"]
            print(f"Participant Joined: Name={participant_name}, Meeting ID={meeting_id}")

        elif data.get("event") == "app.installed":
            account_id = data["payload"]["account_id"]
            print(f"App installed in account {account_id}")
            return {"plainToken": ZOOM_WEBHOOK_VERIFICATION_TOKEN}

        elif data.get("event") == "app.uninstalled":
            account_id = data["payload"]["account_id"]
            print(f"App uninstalled from account {account_id}")

        else:
            print(f"Received unknown event: {event_type}")
            print(f"Webhook Data: {data}")  # Log the entire payload for debugging unknown events


        return {"status": "success"}

    except Exception as e:
        print(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Error processing webhook")