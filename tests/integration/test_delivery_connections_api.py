import pytest
from sqlalchemy import select

from backend.auth import crypto
from backend.models.delivery_connection import DeliveryConnection

SECRET = "app-secret-must-not-appear"


@pytest.mark.asyncio
async def test_connection_crud_masks_secret(client, db_session):
    created = await client.post("/api/v1/delivery-connections", json={
        "name": "Feishu", "app_id": "cli_test", "app_secret": SECRET,
    })
    assert created.status_code == 201
    assert SECRET not in created.text
    connection_id = created.json()["data"]["id"]
    listed = await client.get("/api/v1/delivery-connections")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["has_app_secret"] is True
    assert SECRET not in listed.text
    ciphertext = (
        await db_session.execute(
            select(DeliveryConnection).where(DeliveryConnection.id == connection_id)
        )
    ).scalar_one()._app_secret_encrypted
    updated = await client.patch(
        f"/api/v1/delivery-connections/{connection_id}", json={"name": "Renamed"}
    )
    assert updated.status_code == 200
    row = await db_session.get(DeliveryConnection, connection_id)
    assert row is not None
    assert row._app_secret_encrypted == ciphertext
    assert row.app_id == "cli_test"
    assert (await client.delete(f"/api/v1/delivery-connections/{connection_id}")).status_code == 200


@pytest.mark.asyncio
async def test_connection_patch_rejects_explicit_null(client):
    created = await client.post(
        "/api/v1/delivery-connections",
        json={"name": "Feishu", "app_id": "cli_test", "app_secret": SECRET},
    )
    connection_id = created.json()["data"]["id"]
    response = await client.patch(
        f"/api/v1/delivery-connections/{connection_id}", json={"enabled": None}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_connection_create_fails_closed_without_encryption_key(
    client, db_session, monkeypatch
):
    monkeypatch.setenv(crypto.ENV_KEY, "")
    response = await client.post(
        "/api/v1/delivery-connections",
        json={"name": "Feishu", "app_id": "cli_test", "app_secret": SECRET},
    )
    assert response.status_code == 503
    assert SECRET not in response.text
    assert (await db_session.execute(select(DeliveryConnection))).scalars().all() == []


@pytest.mark.asyncio
async def test_probe_failure_is_typed_and_redacted(client, monkeypatch):
    created = await client.post(
        "/api/v1/delivery-connections",
        json={"name": "Feishu", "app_id": "cli_test", "app_secret": SECRET},
    )
    connection_id = created.json()["data"]["id"]

    async def fail_probe(*_args, **_kwargs):
        from backend.services.feishu_bitable_delivery import FeishuDeliveryError

        raise FeishuDeliveryError("target_unavailable")

    monkeypatch.setattr(
        "backend.api.v1.delivery_connections.probe_bitable", fail_probe
    )
    response = await client.post(
        f"/api/v1/delivery-connections/{connection_id}/probe",
        json={"app_token": "sensitive-target", "table_id": "table"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["error_kind"] == "target_unavailable"
    assert SECRET not in response.text
    assert "sensitive-target" not in response.text
