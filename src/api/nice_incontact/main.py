"""
NICE inContact Callback Queue API
Production FastAPI service for NICE inContact integration
"""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
import requests
import os
from dotenv import load_dotenv
from auth import get_access_token, invalidate_token

load_dotenv()

app = FastAPI(
    title="NICE inContact Callback Queue API",
    description="API for managing callback queues in NICE inContact",
    version="1.0.0"
)

# NICE inContact API Configuration
API_URL = "https://api-na2.niceincontact.com"
QUEUE_CALLBACK_ENDPOINT = "incontactAPI/services/v33.0/queuecallback"
DEFAULT_SKILL_ID = 4354630  # Static skill ID for all requests


def _normalize_phone(raw: str) -> str:
    """
    NICE inContact queuecallback expects a 10-digit US number (no country code).
    Strip all non-digits, then remove a leading '1' if the result is 11 digits.
    Examples:
        '+12407559064'  → '2407559064'
        '2407559064'    → '2407559064'
        '(240) 755-9064'→ '2407559064'
    """
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


# ===== REQUEST MODELS =====
class CallbackQueueRequest(BaseModel):
    """Simplified model for creating callback queue"""
    phoneNumber: str = Field(..., description="Customer phone number", example="2407559064")
    skill: int = Field(default=DEFAULT_SKILL_ID, description="Skill ID for routing")

    class Config:
        json_schema_extra = {
            "example": {
                "phoneNumber": "2407559064",
                "skill": 4354630
            }
        }


class CallbackQueueResponse(BaseModel):
    """Response model"""
    success: bool
    message: str
    contactId: Optional[int] = None
    data: Optional[dict] = None


# ===== HELPER FUNCTION =====
def post_api(url: str, method: str, record: dict, headers: dict):
    """
    Make API request to NICE inContact with auto token refresh.
    """
    response = requests.post(url, json=record, headers=headers, verify=False)
    
    # Handle 401 - token expired
    if response.status_code == 401:
        print("⚠️ Token expired, refreshing...")
        invalidate_token()
        token = get_access_token(force_refresh=True)
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to refresh access token"
            )
        
        headers["Authorization"] = f"Bearer {token}"
        response = requests.post(url, json=record, headers=headers, verify=False)
    
    return response


# ===== API ENDPOINTS =====
@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "NICE inContact Callback Queue API",
        "version": "1.0.0",
        "api_url": API_URL
    }


@app.post(
    "/callback-queue",
    response_model=CallbackQueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Callback Queue"]
)
async def create_callback_queue(request: CallbackQueueRequest):
    """
    Create a new callback queue entry in NICE inContact
    
    - **phoneNumber**: Customer phone number (required)
    - **skill**: Skill ID for routing (default: 4354630)
    """
    
    # Get access token
    token = get_access_token()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to obtain access token"
        )
    
    # Build URL
    url = f"{API_URL}/{QUEUE_CALLBACK_ENDPOINT}"
    
    # Build headers as specified
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Authorization": f"Bearer {token}"
    }
    
    # Normalise phone: NICE expects 10-digit US number, no country code
    phone = _normalize_phone(request.phoneNumber)

    # Minimal required payload per NICE inContact queuecallback v33 spec:
    # - "skill"       int32   REQUIRED
    # - "phoneNumber" string  REQUIRED
    # - "callDelay"   int32   optional (include as 0 to satisfy strict validators)
    # - "priorityManagement" is a STRING enum if needed — NOT an object
    record = {
        "skill":       request.skill,
        "phoneNumber": phone,
        "callDelay":   0,
    }

    try:
        # Call NICE inContact API
        response = post_api(url, "POST", record=record, headers=headers)

        # Log full response body so every 400 error is visible in docker logs
        if response.status_code != 202:
            try:
                body = response.json()
            except Exception:
                body = response.text
            print(
                f"NICE API {response.status_code} | payload={record} | response={body}",
                flush=True,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "Failed to create callback queue",
                    "error": str(body),
                    "status_code": response.status_code,
                },
            )

        data = response.json()
        return CallbackQueueResponse(
            success=True,
            message="Callback queue created successfully",
            contactId=data.get("contactId"),
        )

    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API request failed: {exc}",
        )


@app.get("/skills", tags=["Skills"])
async def get_skills():
    """Get all available skills from NICE inContact"""
    token = get_access_token()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to obtain access token"
        )
    
    url = f"{API_URL}/incontactAPI/services/v33.0/skills"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(url, headers=headers, verify=False)
        
        if response.status_code == 200:
            return {
                "success": True,
                "data": response.json()
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch skills: {response.text}"
            )
    
    except requests.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API request failed: {str(e)}"
        )


# ===== RUN THE APP =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)