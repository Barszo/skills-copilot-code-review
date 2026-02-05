"""
Announcement management endpoints for the High School Management System API
"""

from datetime import date, datetime, timezone
import logging
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    message: str = Field(..., min_length=3, max_length=500)
    start_date: Optional[date] = None
    end_date: date


class AnnouncementResponse(BaseModel):
    id: str
    title: str
    message: str
    start_date: Optional[str]
    end_date: str
    created_at: str
    updated_at: str


def require_teacher(username: Optional[str]) -> None:
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")


def date_to_utc_datetime(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def serialize_announcement(doc) -> AnnouncementResponse:
    start_date = doc.get("start_date")
    end_date = doc.get("end_date")
    created_at = doc.get("created_at")
    updated_at = doc.get("updated_at")

    return AnnouncementResponse(
        id=str(doc.get("_id")),
        title=doc.get("title", ""),
        message=doc.get("message", ""),
        start_date=start_date.date().isoformat() if start_date else None,
        end_date=end_date.date().isoformat() if end_date else "",
        created_at=created_at.isoformat() if created_at else "",
        updated_at=updated_at.isoformat() if updated_at else ""
    )


def validate_date_range(start_date: Optional[date], end_date: date) -> None:
    if start_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="Start date must be on or before the expiration date"
        )


@router.get("", response_model=List[AnnouncementResponse])
@router.get("/", response_model=List[AnnouncementResponse])
def list_announcements(
    active: bool = Query(False),
    teacher_username: Optional[str] = Query(None)
) -> List[AnnouncementResponse]:
    """
    Get announcements.

    - active: When true, returns only currently active announcements.
    """
    query = {}

    if not active:
        require_teacher(teacher_username)

    if active:
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        query = {
            "end_date": {"$gte": today},
            "$or": [
                {"start_date": {"$exists": False}},
                {"start_date": None},
                {"start_date": {"$lte": today}}
            ]
        }

    try:
        cursor = announcements_collection.find(query)
        if active:
            cursor = cursor.sort("end_date", 1)
        else:
            cursor = cursor.sort("end_date", -1)

        return [serialize_announcement(doc) for doc in cursor]
    except Exception as exc:
        logger.exception("Failed to list announcements")
        raise HTTPException(status_code=500, detail="Request failed") from exc


@router.post("", response_model=AnnouncementResponse)
@router.post("/", response_model=AnnouncementResponse)
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementResponse:
    """Create a new announcement - requires teacher authentication."""
    require_teacher(teacher_username)
    validate_date_range(payload.start_date, payload.end_date)

    now = datetime.now(timezone.utc)
    doc = {
        "title": payload.title.strip(),
        "message": payload.message.strip(),
        "start_date": date_to_utc_datetime(payload.start_date)
        if payload.start_date
        else None,
        "end_date": date_to_utc_datetime(payload.end_date),
        "created_at": now,
        "updated_at": now
    }

    try:
        result = announcements_collection.insert_one(doc)
        saved = announcements_collection.find_one({"_id": result.inserted_id})
        return serialize_announcement(saved)
    except Exception as exc:
        logger.exception("Failed to create announcement")
        raise HTTPException(status_code=500, detail="Request failed") from exc


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementResponse:
    """Update an announcement - requires teacher authentication."""
    require_teacher(teacher_username)
    validate_date_range(payload.start_date, payload.end_date)

    try:
        announcement_object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Announcement not found") from exc

    update_doc = {
        "$set": {
            "title": payload.title.strip(),
            "message": payload.message.strip(),
            "start_date": date_to_utc_datetime(payload.start_date)
            if payload.start_date
            else None,
            "end_date": date_to_utc_datetime(payload.end_date),
            "updated_at": datetime.now(timezone.utc)
        }
    }

    try:
        result = announcements_collection.update_one(
            {"_id": announcement_object_id},
            update_doc
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")

        saved = announcements_collection.find_one({"_id": announcement_object_id})
        return serialize_announcement(saved)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to update announcement")
        raise HTTPException(status_code=500, detail="Request failed") from exc


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
):
    """Delete an announcement - requires teacher authentication."""
    require_teacher(teacher_username)

    try:
        announcement_object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Announcement not found") from exc

    try:
        result = announcements_collection.delete_one({"_id": announcement_object_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Announcement not found")

        return {"message": "Announcement deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete announcement")
        raise HTTPException(status_code=500, detail="Request failed") from exc
