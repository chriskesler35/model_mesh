"""API key authentication middleware."""

import os
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings

security = HTTPBearer()


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Verify API key for MVP authentication."""
    # Skip auth in development if no key configured
    if settings.modelmesh_api_key == "modelmesh_local_dev_key":
        # Still require the header, but accept dev key
        if credentials.credentials == "modelmesh_local_dev_key":
            return credentials.credentials
    
    if credentials.credentials != settings.modelmesh_api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "type": "authentication_error",
                    "message": "Invalid API key",
                    "code": "invalid_api_key"
                }
            }
        )
    
    return credentials.credentials