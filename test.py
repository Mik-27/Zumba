import os
import requests
import base64
import hashlib
from urllib.parse import quote_plus
from fastapi import FastAPI, Request, HTTPException, Depends, status, Cookie, Response
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
import pymongo
from cryptography.fernet import Fernet  # For encryption
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from datetime import datetime, timedelta
import jwt  # Import the JWT library

load_dotenv()

app = FastAPI(redirect_slashes=False)  # Disable automatic redirecting of slashes

# --- Configuration ---
ZOOM_CLIENT_ID = os.getenv('ZOOM_CLIENT_ID')
ZOOM_CLIENT_SECRET = os.getenv('ZOOM_CLIENT_SECRET')
ZOOM_REDIRECT_URI = os.getenv('ZOOM_REDIRECT_URI')
MONGODB_USER = os.getenv('MONGODB_USER')  # Default MongoDB URI
MONGODB_PWD = os.getenv('MONGODB_PWD')  # Default MongoDB URI
encoded_username = quote_plus(MONGODB_USER)
encoded_password = quote_plus(MONGODB_PWD)
MONGODB_URI=f"mongodb+srv://{encoded_username}:{encoded_password}@zoomcluster.9kalesj.mongodb.net/?retryWrites=true&w=majority&appName=ZoomCluster"
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', os.urandom(32).hex())
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
JWT_EXPIRY_SECONDS = int(os.getenv('JWT_EXPIRY_SECONDS', '3600'))  # In seconds

# --- CORS Middleware (adjust for production!) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your frontend's domain(s)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MongoDB Setup ---
DATABASE_NAME = 'zoom_gamification'  # MongoDB database name
client = pymongo.MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]  # Use brackets to access the database
zoom_users_collection = db.zoom_users  # Use a collection name

# --- Encryption Setup ---
def generate_key(password: str) -> str:
    """Generates a Fernet encryption key from a password using PBKDF2HMAC."""
    password_provided = password.encode()
    salt = b'snkjsadvcubroyuaiufvnbvmiodhofstiisudhkjsdfkm'  # CHANGE THIS - SHOULD be random and stored securely
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(password_provided))
    return key.decode()

# Setup encryption key
print("Encryption Key: ", ENCRYPTION_KEY)
if not ENCRYPTION_KEY:
    print("ENCRYPTION_KEY not found. Generating and storing securely... (THIS IS NOT SECURE)")
    # **Correct way to generate the Fernet key**
    key = Fernet.generate_key()
    ENCRYPTION_KEY = key.decode()  # Store the string representation
    print(f"Generated Key: {ENCRYPTION_KEY}") #For demonstration purposes only

else:
    try:
        Fernet(ENCRYPTION_KEY.encode()) #Validates if the environment variable is a valid key.
    except Exception as err:
        print(f"Encryption key invalid. Error - {err}")
# Create the Fernet object (use the key you loaded)
fernet = Fernet(ENCRYPTION_KEY.encode())


def encrypt(text: bytes) -> bytes:
    """Encrypts the given text."""
    return fernet.encrypt(text)

def decrypt(token: bytes) -> bytes:
    """Decrypts the given text."""
    return fernet.decrypt(token)

# --- JWT Functions ---
def generate_jwt(zoom_user_id: str, secret_key: str, algorithm: str, expiry_seconds: int) -> str:
    """Generates a JWT token for authentication."""
    payload = {
        'zoom_user_id': zoom_user_id,
        'exp': datetime.utcnow() + timedelta(seconds=expiry_seconds)
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)

def decode_jwt(token: str, secret_key: str, algorithm: str) -> dict | None:
    """Decodes a JWT token."""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # Token has expired
    except jwt.InvalidTokenError:
        return None  # Token is invalid


# --- OAuth 2.0 Flow ---
@app.get("/login/zoom")
async def login_zoom():
    """Redirects the user to Zoom's OAuth authorization page."""
    scopes = "meeting:read user:read meeting:read:list_meetings meeting:read:list_past_participants meeting:read:meeting_chat meeting:write:poll meeting:read:poll meeting:write:meeting zoomapp:inmeeting"
    auth_url = (
        f"https://zoom.us/oauth/authorize?response_type=code"
        f"&client_id={ZOOM_CLIENT_ID}"
        f"&redirect_uri={ZOOM_REDIRECT_URI}"
        f"&scope={scopes}"  # Make sure to include scopes here
    )
    return RedirectResponse(url=auth_url)


@app.get("/auth/zoom/callback")
async def zoom_callback(request: Request, code: str = None, error: str = None, response: Response = None):
    """Handles the redirect back from Zoom after authorization and exchanges code for tokens."""
    print("Here in the callback")
    print(error)
    if error:
        raise HTTPException(status_code=400, detail=f"Error during Zoom authentication: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Authorization code missing.")

    token_url = "https://zoom.us/oauth/token"
    auth_header = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': ZOOM_REDIRECT_URI
    }

    try:
        response = requests.post(token_url, headers=headers, data=payload)
        response.raise_for_status()
        token_data = response.json()

        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in')

        if not access_token:
            raise HTTPException(status_code=500, detail="Failed to retrieve access token.")

        user_info_url = "https://api.zoom.us/v2/users/me"
        user_headers = {'Authorization': f'Bearer {access_token}'}
        user_response = requests.get(user_info_url, headers=user_headers)
        user_response.raise_for_status()
        user_info = user_response.json()
        zoom_user_id = user_info.get('id')
        user_email = user_info.get('email')


        # --- Store Tokens and User Data in MongoDB (Encrypted) ---
        try:
            # Encrypt the tokens before storing
            encrypted_access_token = encrypt(access_token.encode())
            encrypted_refresh_token = encrypt(refresh_token.encode())
            expiry_time = datetime.utcnow() + timedelta(seconds=expires_in)

            # Check if zoom user already exists. We don't want to have duplicate entries.
            existing_zoom_user = zoom_users_collection.find_one({"zoom_user_id": zoom_user_id})

            if existing_zoom_user:
                print("Zoom user found, updating database")
                zoom_users_collection.update_one({"zoom_user_id": zoom_user_id},
                    { "$set": {
                            'encrypted_access_token': encrypted_access_token,
                            'encrypted_refresh_token': encrypted_refresh_token,
                            'access_token_expiry': expiry_time
                        }
                    }
                )
            else:
                print("Zoom user not found, creating entry in database")
                zoom_users_collection.insert_one({
                    'zoom_user_id': zoom_user_id,
                    'user_email': user_email,
                    'encrypted_access_token': encrypted_access_token,
                    'encrypted_refresh_token': encrypted_refresh_token,
                    'access_token_expiry': expiry_time
                })
        except pymongo.errors.PyMongoError as e:
            print(f"Database error: {e}")
            raise HTTPException(status_code=500, detail="Database error occurred during token storage.")


        # Generate JWT Token
        jwt_token = generate_jwt(zoom_user_id, JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRY_SECONDS)

        # Set Cookie for Session Management (HTTPS only in production)
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER) # Use 303 to ensure GET method
        response.set_cookie(key="jwt_token", value=jwt_token, httponly=True, secure=False, samesite="lax") # adjust secure and samesite for production
        return response

    except requests.exceptions.RequestException as e:
        print(f"Error exchanging token or getting user info: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            try:
                print(f"Response body: {e.response.json()}")
            except ValueError:
                print(f"Response body: {e.response.text()}")
        raise HTTPException(status_code=500, detail="An error occurred during Zoom authentication.")

# --- JWT Authentication Dependency ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") #not actually using password flow, but needed for dependency

async def get_zoom_user_id_from_jwt(jwt_token: str | None = Cookie(default=None)) -> str:
    """Retrieves and validates the Zoom user ID from the JWT token."""
    if not jwt_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_jwt(jwt_token, JWT_SECRET_KEY, JWT_ALGORITHM)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    zoom_user_id = payload.get('zoom_user_id')
    if not zoom_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return zoom_user_id

# --- Retrieve Access Token Function ---
async def get_zoom_access_token(zoom_user_id: str) -> str | None:
    """Retrieves the decrypted Zoom access token from MongoDB."""
    try:
        zoom_user = zoom_users_collection.find_one({"zoom_user_id": zoom_user_id})
        if not zoom_user:
            return None  # Zoom user not found in database

        encrypted_access_token = zoom_user.get('encrypted_access_token')
        access_token = decrypt(encrypted_access_token).decode()
        return access_token

    except pymongo.errors.PyMongoError as e:
        print(f"Database error during access token retrieval: {e}")
        raise HTTPException(status_code=500, detail="Database error")


# --- Secured Route Example ---
@app.get("/dashboard")
async def dashboard(zoom_user_id: str = Depends(get_zoom_user_id_from_jwt)):
    """Example secured route: requires a valid JWT."""
    access_token = await get_zoom_access_token(zoom_user_id)

    if not access_token:
        raise HTTPException(status_code=500, detail="Unable to retrieve access token")
    # Use access token for API calls here
    return {"message": f"Welcome! Zoom User ID: {zoom_user_id}. You have an Access Token."}

# --- Logout Route ---
@app.get("/logout")
async def logout(response: Response):
    """Logs out the user by clearing the JWT cookie."""
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)  # Use 303 for GET redirect
    response.delete_cookie("jwt_token")
    return response

# --- Start the FastAPI application ---
if __name__ == "__main__":
    print("Ensure the following environment variables are setup: ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET, ZOOM_REDIRECT_URI, MONGODB_URI, ENCRYPTION_KEY, JWT_SECRET_KEY")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)