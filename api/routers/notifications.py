"""
Real-time notifications via Server-Sent Events (SSE).

Clients can subscribe to campaign status updates, credit changes,
and system-level events by connecting to the /notifications/stream endpoint.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Campaign, User
from ..auth import get_current_user_id

logger = logging.getLogger("leadfactory.notifications")

router = APIRouter(prefix="/notifications", tags=["notifications"])

# In-memory event bus for SSE (per-user queues)
_user_queues: dict[str, list[asyncio.Queue]] = {}


def publish_event(user_id: str, event_type: str, data: dict) -> None:
    """Publish an event to all SSE subscribers for a given user."""
    queues = _user_queues.get(user_id, [])
    event = {"type": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()}
    for q in queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Drop if client is too slow


async def _event_generator(user_id: str, request: Request):
    """Generate SSE events for a specific user."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    if user_id not in _user_queues:
        _user_queues[user_id] = []
    _user_queues[user_id].append(queue)

    try:
        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

        while True:
            if await request.is_disconnected():
                break

            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
            except asyncio.TimeoutError:
                # Send keepalive ping every 30s
                yield f": keepalive\n\n"
    finally:
        _user_queues.get(user_id, []).remove(queue) if queue in _user_queues.get(user_id, []) else None
        if user_id in _user_queues and not _user_queues[user_id]:
            del _user_queues[user_id]


@router.get("/stream")
async def notification_stream(
    request: Request,
    token: str = Query(..., description="JWT bearer token (passed as query param for SSE)"),
):
    """Subscribe to real-time notifications via Server-Sent Events.

    Since EventSource API doesn't support Authorization headers,
    pass the JWT token as a query parameter.
    """
    from ..auth import decode_token

    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return StreamingResponse(
        _event_generator(user_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/test")
async def send_test_notification(
    user_id: str = Depends(get_current_user_id),
):
    """Send a test notification to the current user (for development/testing)."""
    publish_event(user_id, "test", {"message": "This is a test notification"})
    return {"status": "sent"}
