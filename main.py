from fastapi import FastAPI, Request, Depends, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2AuthorizationCodeBearer
from urllib.parse import urlencode
import httpx
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from a .env file if you have one

# **IMPORTANT: Replace these with your actual Zoom OAuth app credentials**
ZOOM_CLIENT_ID = os.environ.get("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.environ.get("ZOOM_CLIENT_SECRET")
ZOOM_REDIRECT_URI = os.environ.get("ZOOM_REDIRECT_URI")  # e.g., "http://localhost:8000/callback"
ZOOM_AUTHORIZATION_URL = "https://zoom.us/oauth/authorize"
ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_USER_INFO_URL = "https://api.zoom.us/v2/users/me"


app = FastAPI()

templates = Jinja2Templates(directory="templates") # Create a "templates" directory and put your HTML files in it.

oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=ZOOM_AUTHORIZATION_URL,
    tokenUrl=ZOOM_TOKEN_URL
)


async def get_zoom_user_info(access_token: str):
    """Fetches user information from Zoom API."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(ZOOM_USER_INFO_URL, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Error fetching user info: {e}")
            return None
        except httpx.RequestError as e:
            print(f"Request error: {e}")
            return None


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Main landing page with the Zoom login button."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login")
async def zoom_login():
    """Redirects the user to Zoom's authorization page."""
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
        "redirect_uri": ZOOM_REDIRECT_URI,
        "client_id": ZOOM_CLIENT_ID,
        "client_secret": ZOOM_CLIENT_SECRET
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(ZOOM_TOKEN_URL, data=token_params)
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to obtain access token from Zoom.")

            user_info = await get_zoom_user_info(access_token)

            if not user_info:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve user info from Zoom.")


            return templates.TemplateResponse("success.html", {"request": request, "user_info": user_info})


        except httpx.HTTPStatusError as e:
            print(f"Error during token exchange: {e}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Token Exchange Failed: {e}")
        except httpx.RequestError as e:
            print(f"Request error during token exchange: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Token Exchange Request Failed: {e}")

