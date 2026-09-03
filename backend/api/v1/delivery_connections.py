from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.crypto import CredentialCryptoError
from backend.database import get_db
from backend.models.delivery_connection import DeliveryAttempt, DeliveryConnection
from backend.schemas.common import ApiResponse
from backend.schemas.delivery_connection import (
    DeliveryConnectionCreate,
    DeliveryConnectionRead,
    DeliveryConnectionUpdate,
    FeishuBitableTargetProbe,
)
from backend.services.feishu_bitable_delivery import FeishuDeliveryError, probe_bitable

router = APIRouter(prefix="/delivery-connections", tags=["delivery-connections"])


async def _row(db: AsyncSession, connection_id: str) -> DeliveryConnection:
    query = select(DeliveryConnection).where(DeliveryConnection.id == connection_id)
    row = (await db.execute(query)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Delivery connection not found")
    return row


@router.get("", response_model=ApiResponse[list[DeliveryConnectionRead]])
async def list_connections(db: AsyncSession = Depends(get_db)) -> ApiResponse:
    query = select(DeliveryConnection).order_by(DeliveryConnection.created_at.desc())
    rows = (await db.execute(query)).scalars().all()
    return ApiResponse.ok([DeliveryConnectionRead.from_model(row) for row in rows])


@router.post("", response_model=ApiResponse[DeliveryConnectionRead], status_code=201)
async def create_connection(
    body: DeliveryConnectionCreate, db: AsyncSession = Depends(get_db)
) -> ApiResponse:
    try:
        row = DeliveryConnection(
            name=body.name, app_id=body.app_id, app_secret=body.app_secret, enabled=body.enabled
        )
    except CredentialCryptoError as exc:
        raise HTTPException(503, "Credential encryption is not configured") from exc
    db.add(row)
    await db.flush()
    return ApiResponse.ok(DeliveryConnectionRead.from_model(row))


@router.patch("/{connection_id}", response_model=ApiResponse[DeliveryConnectionRead])
async def update_connection(
    connection_id: str,
    body: DeliveryConnectionUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    row = await _row(db, connection_id)
    changes = body.model_dump(exclude_unset=True)
    if "app_id" in changes:
        attempts = await db.scalar(
            select(DeliveryAttempt.id)
            .where(DeliveryAttempt.connection_id == connection_id)
            .limit(1)
        )
        if attempts is not None:
            raise HTTPException(409, "App ID cannot change after delivery history exists")
    try:
        for field, value in changes.items():
            setattr(row, field, value)
    except CredentialCryptoError as exc:
        raise HTTPException(503, "Credential encryption is not configured") from exc
    await db.flush()
    return ApiResponse.ok(DeliveryConnectionRead.from_model(row))


@router.delete("/{connection_id}", response_model=ApiResponse[None])
async def delete_connection(connection_id: str, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    row = await _row(db, connection_id)
    attempts = await db.scalar(
        select(DeliveryAttempt.id).where(DeliveryAttempt.connection_id == connection_id).limit(1)
    )
    if attempts is not None:
        raise HTTPException(409, "Connection with delivery history cannot be deleted")
    await db.delete(row)
    return ApiResponse.ok(None)


@router.post("/{connection_id}/probe", response_model=ApiResponse[dict])
async def probe_connection(
    connection_id: str,
    body: FeishuBitableTargetProbe,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    row = await _row(db, connection_id)
    if not row.enabled:
        raise HTTPException(422, "Delivery connection is disabled")
    try:
        return ApiResponse.ok(await probe_bitable(row, body.app_token, body.table_id))
    except CredentialCryptoError as exc:
        raise HTTPException(503, "Credential encryption is not configured") from exc
    except FeishuDeliveryError as exc:
        detail = {"error_kind": exc.kind, "message": "Feishu target validation failed"}
        raise HTTPException(502, detail=detail) from exc
