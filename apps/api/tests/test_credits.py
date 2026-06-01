"""Tests for credit ledger endpoints."""

from uuid import uuid4

import pytest
from fastapi import status

from ceq_api.auth import get_current_user
from ceq_api.models import CreditLedgerEntry, CreditLedgerType


async def _override_admin(mock_admin_user):
    return mock_admin_user


class TestCreditBalance:
    def test_balance_starts_at_zero(self, client):
        response = client.get("/v1/credits/balance")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["balance"] == 0

    @pytest.mark.asyncio
    async def test_balance_sums_user_ledger_only(self, async_client, db_session, mock_user):
        db_session.add_all(
            [
                CreditLedgerEntry(
                    user_id=mock_user.id,
                    org_id=mock_user.org_id,
                    amount=500,
                    transaction_type=CreditLedgerType.GRANT.value,
                    reason="welcome grant",
                    idempotency_key="welcome-grant",
                    ledger_metadata={},
                ),
                CreditLedgerEntry(
                    user_id=mock_user.id,
                    org_id=mock_user.org_id,
                    amount=-125,
                    transaction_type=CreditLedgerType.DEBIT.value,
                    reason="template run",
                    idempotency_key="job-debit",
                    ledger_metadata={"job_id": "example"},
                ),
                CreditLedgerEntry(
                    user_id=uuid4(),
                    amount=999,
                    transaction_type=CreditLedgerType.GRANT.value,
                    reason="other user",
                    idempotency_key="other-user-grant",
                    ledger_metadata={},
                ),
            ]
        )
        await db_session.flush()

        response = await async_client.get("/v1/credits/balance")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["balance"] == 375


class TestCreditLedger:
    @pytest.mark.asyncio
    async def test_ledger_lists_user_entries_only(self, async_client, db_session, mock_user):
        own_entry = CreditLedgerEntry(
            user_id=mock_user.id,
            org_id=mock_user.org_id,
            amount=100,
            transaction_type=CreditLedgerType.GRANT.value,
            reason="own grant",
            idempotency_key="own-grant",
            ledger_metadata={},
        )
        other_entry = CreditLedgerEntry(
            user_id=uuid4(),
            amount=250,
            transaction_type=CreditLedgerType.GRANT.value,
            reason="other grant",
            idempotency_key="other-grant",
            ledger_metadata={},
        )
        db_session.add_all([own_entry, other_entry])
        await db_session.flush()

        response = await async_client.get("/v1/credits/ledger")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert data["entries"][0]["idempotency_key"] == "own-grant"


class TestCreditGrants:
    def test_grant_requires_admin(self, client, mock_user):
        response = client.post(
            "/v1/credits/grants",
            json={
                "user_id": str(mock_user.id),
                "org_id": str(mock_user.org_id),
                "amount": 100,
                "reason": "welcome grant",
                "idempotency_key": "grant-requires-admin",
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_admin_grant_creates_idempotent_entry(
        self,
        app,
        async_client,
        mock_admin_user,
        mock_user,
    ):
        async def admin_user():
            return await _override_admin(mock_admin_user)

        app.dependency_overrides[get_current_user] = admin_user

        payload = {
            "user_id": str(mock_user.id),
            "org_id": str(mock_user.org_id),
            "amount": 250,
            "reason": "pilot grant",
            "idempotency_key": "pilot-grant-001",
            "metadata": {"source": "test"},
        }

        first = await async_client.post("/v1/credits/grants", json=payload)
        second = await async_client.post("/v1/credits/grants", json=payload)

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_201_CREATED
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["amount"] == 250
        assert first.json()["ledger_metadata"] == {"source": "test"}

    @pytest.mark.asyncio
    async def test_admin_grant_rejects_idempotency_key_reuse_with_different_payload(
        self,
        app,
        async_client,
        mock_admin_user,
        mock_user,
    ):
        async def admin_user():
            return await _override_admin(mock_admin_user)

        app.dependency_overrides[get_current_user] = admin_user

        base_payload = {
            "user_id": str(mock_user.id),
            "amount": 250,
            "reason": "pilot grant",
            "idempotency_key": "pilot-grant-conflict",
        }

        first = await async_client.post("/v1/credits/grants", json=base_payload)
        second = await async_client.post(
            "/v1/credits/grants",
            json={**base_payload, "amount": 251},
        )

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_409_CONFLICT
