from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2AuthorizationCodeBearer
from urllib.parse import urlencode
import httpx
import os
import json
from typing import Optional
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone # Import datetime
from parser import process_webhook


load_dotenv()

# del os.environ["ZOOM_CLIENT_ID"]
# del os.environ["ZOOM_CLIENT_SECRET"]

# --- Zoom Configuration ---
ZOOM_CLIENT_ID = os.environ.get("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.environ.get("ZOOM_CLIENT_SECRET")
# ZOOM_REDIRECT_URI = os.environ.get("ZOOM_REDIRECT_URI", "https://vital-bluegill-deadly.ngrok-free.app/callback")
ZOOM_REDIRECT_URI = "https://vital-bluegill-deadly.ngrok-free.app/callback"
ZOOM_AUTHORIZATION_URL = "https://zoom.us/oauth/authorize"
ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_USER_INFO_URL = "https://api.zoom.us/v2/users/me"
ZOOM_CREATE_MEETING_URL = "https://api.zoom.us/v2/users/me/meetings" # API endpoint for creating meetings
ZOOM_WEBHOOK_SECRET_TOKEN = os.environ.get("ZOOM_WEBHOOK_SECRET_TOKEN")
ZOOM_WEBHOOK_VERIFICATION_TOKEN = os.environ.get("ZOOM_WEBHOOK_VERIFICATION_TOKEN")
ZOOM_POLL_CREATE_URL = "https://api.zoom.us/v2/meetings/" # API endpoint for creating polls
ZOOM_POLL_REPORT_URL="https://api.zoom.us/v2/report/meetings/"

# print(os.environ)
print(f"ZOOM_CLIENT_ID = {ZOOM_CLIENT_ID}")

# --- FastAPI Setup ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- Helper Functions ---
async def get_zoom_user_info(access_token: str):
    """Fetches user information from Zoom API."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(ZOOM_USER_INFO_URL, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Error fetching user info: {e.response.text}") # Log error details
            return None
        except httpx.RequestError as e:
            print(f"Request error fetching user info: {e}")
            return None

# async def get_poll_results(access_token: str, meeting_id: str):
#     """Fetches user information from Zoom API."""
#     headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
#     body = {
#         "id": "QalIoKWLTJehBJ8e1xRrbQ",
#         "status": "notstart",
#         "anonymous": True,
#         "poll_type": 2,
#         "questions": [
#             {
#             "answer_max_character": 200,
#             "answer_min_character": 1,
#             "answer_required": False,
#             "answers": [
#                 "Extremely useful"
#                 ],
#             "case_sensitive": False,
#             "name": "How useful was this meeting?",
#             "prompts": [
#                 {
#                 "prompt_question": "How are you?",
#                 "prompt_right_answers": [
#                     "Good"
#                     ]
#                 }
#             ],
#             "rating_max_label": "Extremely Likely",
#             "rating_max_value": 4,
#             "rating_min_label": "Not likely",
#             "rating_min_value": 0,
#             "right_answers": [
#                 "Good"
#             ],
#             "show_as_dropdown": False,
#             "type": "single"
#             }
#         ],
#         "title": "Learn something new"
#     }

#     async with httpx.AsyncClient() as client:
#         try:
#             url = ZOOM_POLL_CREATE_URL + meeting_id + "/polls"
#             print(url)
#             response = await client.post(url, headers=headers, json=body)
#             response.raise_for_status()
#             return response.json()
#         except httpx.HTTPStatusError as e:
#             print(f"Error fetching user info: {e.response.text}") # Log error details
#             return None
#         except httpx.RequestError as e:
            print(f"Request error fetching user info: {e}")
            return None


# async def get_poll_info(access_token: str, meeting_id: str):
#     """Fetches user information from Zoom API."""
#     headers = {"Authorization": f"Bearer {access_token}"}
#     async with httpx.AsyncClient() as client:
#         try:
#             url = ZOOM_POLL_REPORT_URL + meeting_id + "/polls"
#             response = await client.get(url, headers=headers)
#             response.raise_for_status()
#             return response.json()
#         except httpx.HTTPStatusError as e:
#             print(f"Error fetching user info: {e.response.text}") # Log error details
#             return None
#         except httpx.RequestError as e:
#             print(f"Request error fetching user info: {e}")
#             return None


async def create_zoom_meeting(access_token: str, topic: str, start_time_str: str, duration_min: int):
    """Creates a new meeting using the Zoom API."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    # Convert local datetime string from form to UTC ISO format for Zoom API
    try:
        naive_dt = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
        local_dt = naive_dt.astimezone()
        utc_dt = local_dt.astimezone(timezone.utc)
        start_time_iso = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    except ValueError:
         raise ValueError("Invalid start time format. Please use YYYY-MM-DDTHH:MM.")


    payload = {
        "topic": topic,
        "type": 2,  # 1=Instant, 2=Scheduled, 3=Recurring(no fixed time), 8=Recurring(fixed time)
        "start_time": start_time_iso,
        "duration": duration_min,  # In minutes
        "timezone": "UTC", # API requires timezone for start_time
        "settings": {
            "join_before_host": True,
            "mute_upon_entry": False,
            "participant_video": True,
            "host_video": True,
            "auto_recording": "none" # cloud, local, none
            # Add other settings as needed
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            print(f"Creating meeting with payload: {payload}") # Debugging
            response = await client.post(ZOOM_CREATE_MEETING_URL, headers=headers, json=payload)
            print(f"Zoom API Response Status: {response.status_code}") # Debugging
            print(f"Zoom API Response Body: {response.text}") # Debugging
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Error creating meeting: {e.response.status_code} - {e.response.text}")
            # Propagate a more informative error
            error_detail = f"Zoom API Error ({e.response.status_code}): "
            try:
                 error_detail += e.response.json().get('message', e.response.text)
            except: # If response is not JSON
                 error_detail += e.response.text
            raise HTTPException(status_code=e.response.status_code, detail=error_detail)
        except httpx.RequestError as e:
            print(f"Request error creating meeting: {e}")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Network error communicating with Zoom: {e}")
        except ValueError as e: # Catch the specific ValueError from time parsing
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# --- FastAPI Routes ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Main landing page with the Zoom login button."""
    # Clear any previous session info if needed (implementation depends on session mechanism)
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login")
async def zoom_login():
    """Redirects the user to Zoom's authorization page."""
    # Consider adding a 'state' parameter for CSRF protection in production
    params = {
        "response_type": "code",
        "client_id": ZOOM_CLIENT_ID,
        "redirect_uri": ZOOM_REDIRECT_URI
    }
    authorization_url = f"{ZOOM_AUTHORIZATION_URL}?" + urlencode(params)
    return RedirectResponse(authorization_url)

@app.get("/callback")
async def zoom_callback(code: str, request: Request):
    """Handles the callback from Zoom after authorization."""
    token_params = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": ZOOM_REDIRECT_URI
    }

    # Basic Auth Header: base64encode(client_id:client_secret)
    auth_header = httpx.BasicAuth(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET)

    async with httpx.AsyncClient() as client:
        try:
            # Use Basic Auth for the token request
            response = await client.post(ZOOM_TOKEN_URL, data=token_params, auth=auth_header)
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to obtain access token from Zoom.")

            user_info = await get_zoom_user_info(access_token)

            if not user_info:
                # Even if user info fails, we might still proceed if token is valid
                 print("Warning: Failed to retrieve user info, but proceeding with access token.")
                 user_info = {"display_name": "Unknown User"} # Provide default

            return templates.TemplateResponse("success.html", {
                "request": request,
                "user_info": user_info,
                "access_token": access_token  # Pass the token here
            })

        except httpx.HTTPStatusError as e:
            print(f"Error during token exchange: {e.response.status_code} - {e.response.text}")
            detail = f"Token Exchange Failed ({e.response.status_code}): "
            try:
                 detail += e.response.json().get('reason', e.response.text)
            except: # If response is not JSON
                 detail += e.response.text
            raise HTTPException(status_code=e.response.status_code, detail=detail)
        except httpx.RequestError as e:
            print(f"Request error during token exchange: {e}")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Token Exchange Request Failed: {e}")


@app.post("/create_meeting", response_class=HTMLResponse)
async def handle_create_meeting(
    request: Request,
    access_token: str = Form(...), # Get token from hidden form field
    topic: str = Form(...),
    start_time: str = Form(...), # Will be string like "YYYY-MM-DDTHH:MM"
    duration: int = Form(...)
):
    """Receives form data and calls the function to create a meeting."""
    # Basic input validation (more can be added)
    if not topic:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meeting topic cannot be empty.")
    if duration <= 0:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duration must be positive.")
    if not access_token:
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token.") # Should not happen if form is correct

    try:
        meeting_details = await create_zoom_meeting(
            access_token=access_token,
            topic=topic,
            start_time_str=start_time,
            duration_min=duration
        )
        # Display meeting details on a confirmation page
        return templates.TemplateResponse("meeting_created.html", {
            "request": request,
            "meeting": meeting_details,
            "request": request,
            "access_token": access_token
        })

    except HTTPException as e:
        # Re-raise HTTPExceptions from create_zoom_meeting or validation
        raise e
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Unexpected error creating meeting: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An internal error occurred: {e}")


@app.post("/webhook")
async def zoom_webhook(request: Request):
    """
    Handles Zoom webhooks for meeting.started and meeting.participant_joined events.
    """
    if not ZOOM_WEBHOOK_VERIFICATION_TOKEN:
        raise HTTPException(status_code=500, detail="ZOOM_WEBHOOK_VERIFICATION_TOKEN not configured")

    if not ZOOM_WEBHOOK_SECRET_TOKEN:
        raise HTTPException(status_code=500, detail="ZOOM_WEBHOOK_SECRET_TOKEN not configured")
    
    # print(request.headers)
    if ZOOM_WEBHOOK_VERIFICATION_TOKEN != request.headers.get("authorization"):
        return {"status": "error", "message": "Invalid secret token"}

    try:
        data = await request.json()
        # if data["payload"]["object"]["participant"]["email"] == "tmihir27+asu@gmail.com":
        print(f"Received webhook data: {data}")
        event_type = data.get("event")
        print(f"Event Type: {event_type}")
        
        # if data['payload']['object']['participant']['email'] != "tmihir27+asu@gmail.com":
        if request.headers.get("x-webhook") == "zoomba":
            print("SENDING TO PARSER")
            process_webhook(data)
        
        # if event_type == "meeting.started":
        #     meeting_id = data["payload"]["object"]["id"]
        #     topic = data["payload"]["object"]["topic"]
        #     start_time = data["payload"]["object"]["start_time"]
        #     print(f"Meeting Started: ID={meeting_id}, Topic='{topic}', Start Time={start_time}")

        # elif event_type == "meeting.participant_joined":
        #     participant_name = data["payload"]["object"]["participant"]["user_name"]
        #     meeting_id = data["payload"]["object"]["id"]
        #     print(f"Participant Joined: Name={participant_name}, Meeting ID={meeting_id}")

        # elif data.get("event") == "app.installed":
        #     account_id = data["payload"]["account_id"]
        #     print(f"App installed in account {account_id}")
        #     return {"plainToken": ZOOM_WEBHOOK_VERIFICATION_TOKEN}

        # elif data.get("event") == "app.uninstalled":
        #     account_id = data["payload"]["account_id"]
        #     print(f"App uninstalled from account {account_id}")

        # else:
        #     print(f"Received unknown event: {event_type}")
        #     print(f"Webhook Data: {data}")

        return {"status": "success"}

    except Exception as e:
        print(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Error processing webhook")
    
# @app.post("/qss_webhook")
# async def zoom_webhook(request: Request):
#     """
#     Handles Zoom webhooks for meeting.started and meeting.participant_joined events.
#     """
#     if not ZOOM_WEBHOOK_VERIFICATION_TOKEN:
#         raise HTTPException(status_code=500, detail="ZOOM_WEBHOOK_VERIFICATION_TOKEN not configured")

#     if not ZOOM_WEBHOOK_SECRET_TOKEN:
#         raise HTTPException(status_code=500, detail="ZOOM_WEBHOOK_SECRET_TOKEN not configured")

#     data = await request.json()

    
# @app.post("/chat_webhook")
# async def zoom_webhook(request: Request):
#     """
#     Handles Zoom webhooks for meeting.started and meeting.participant_joined events.
#     """
#     if not ZOOM_WEBHOOK_VERIFICATION_TOKEN:
#         raise HTTPException(status_code=500, detail="ZOOM_WEBHOOK_VERIFICATION_TOKEN not configured")

#     if not ZOOM_WEBHOOK_SECRET_TOKEN:
#         raise HTTPException(status_code=500, detail="ZOOM_WEBHOOK_SECRET_TOKEN not configured")

#     data = await request.json()
#     print(f"Chat webhook data: {data}")
    

# @app.get("/poll_results", response_class=HTMLResponse)
# async def poll_results(request: Request, access_token: str = Form(...), meeting_id: str = Form(...)):
#     """Receives form data and calls the function to create a meeting."""
#     # Basic input validation (more can be added)
#     if not access_token:
#          raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token.")
#     if not meeting_id:
#          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meeting ID cannot be empty.")
    
#     poll_details = await get_poll_info(
#         access_token=access_token,
#         meeting_id=meeting_id
#     )

#     print(f"Poll Details: {poll_details}") # Debugging


# @app.post("/create_poll", response_class=HTMLResponse)
# async def handle_create_poll(
#     request: Request,
#     access_token: str = Form(...), # Get token from hidden form field
#     meeting_id: str = Form(...),
# ):
#     """Receives form data and calls the function to create a meeting."""
#     # Basic input validation (more can be added)
#     if not access_token:
#          raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token.")
#     if not meeting_id:
#          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meeting ID cannot be empty.")
    
#     poll_details = await get_poll_results(
#         access_token=access_token,
#         meeting_id=meeting_id
#     )

#     print(f"Poll Details: {poll_details}")
