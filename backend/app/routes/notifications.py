"""Notification endpoints — list, read, read-all, delete."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.notification import Notification
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/notifications",
    tags=["notifications"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("")
async def list_notifications(
    request: Request,
    unread_only: bool = False,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List notifications for the current user (unread first, newest first)."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = user.get("id", "owner")

    query = (
        select(Notification)
        .where(Notification.user_id == user_id)
    )
    if unread_only:
        query = query.where(Notification.read == False)

    query = query.order_by(Notification.read.asc(), Notification.created_at.desc()).limit(limit)

    result = await db.execute(query)
    notifications = result.scalars().all()

    unread_count_result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.read == False)
    )
    unread_count = len(unread_count_result.scalars().all())

    return {
        "notifications": [n.to_dict() for n in notifications],
        "unread_count": unread_count,
    }


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = user.get("id", "owner")

    result = await db.execute(
        select(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user_id)
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.read = True
    await db.commit()
    return {"success": True, "notification": notification.to_dict()}


@router.post("/read-all")
async def mark_all_read(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read for the current user."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = user.get("id", "owner")

    await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read == False)
        .values(read=True)
    )
    await db.commit()
    return {"success": True}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a notification."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = user.get("id", "owner")

    result = await db.execute(
        select(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user_id)
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    await db.delete(notification)
    await db.commit()
    return {"success": True}
