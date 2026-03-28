"""User profile schemas."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


# User Profile Schemas
class UserProfileBase(BaseModel):
    name: str = "User"
    email: Optional[str] = None
    preferences: Dict[str, Any] = {}


class UserProfileCreate(UserProfileBase):
    pass


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class UserProfileResponse(UserProfileBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Memory File Schemas
class MemoryFileBase(BaseModel):
    name: str
    content: str = ""
    description: Optional[str] = None


class MemoryFileCreate(MemoryFileBase):
    pass


class MemoryFileUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None


class MemoryFileResponse(MemoryFileBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MemoryFileList(BaseModel):
    data: List[MemoryFileResponse]
    total: int


# Preference Tracking Schemas
class PreferenceBase(BaseModel):
    key: str
    value: str
    source: str = "manual"
    confidence: str = "medium"
    context: Optional[str] = None


class PreferenceCreate(PreferenceBase):
    pass


class PreferenceUpdate(BaseModel):
    value: Optional[str] = None
    confidence: Optional[str] = None
    context: Optional[str] = None


class PreferenceResponse(PreferenceBase):
    id: UUID
    user_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class PreferenceList(BaseModel):
    data: List[PreferenceResponse]
    total: int


# System Modification Schemas
class ModificationBase(BaseModel):
    modification_type: str
    entity_type: str
    entity_id: Optional[UUID] = None
    before_value: Optional[Dict[str, Any]] = None
    after_value: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


class ModificationResponse(ModificationBase):
    id: UUID
    user_id: UUID
    conversation_id: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True


class ModificationList(BaseModel):
    data: List[ModificationResponse]
    total: int