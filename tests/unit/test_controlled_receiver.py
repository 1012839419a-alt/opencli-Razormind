"""Durable controlled receiver table invariants."""

import pytest

from backend.models.delivery_execution import (
    ControlledReceiverDelivery,
    ControlledReceiverNonce,
    DeliveryExecutionResult,
    _reject_immutable_mutation,
)


def test_receiver_durability_keys_are_database_constraints():
    delivery_constraints = {constraint.name for constraint in ControlledReceiverDelivery.__table__.constraints}
    nonce_constraints = {constraint.name for constraint in ControlledReceiverNonce.__table__.constraints}
    result_constraints = {constraint.name for constraint in DeliveryExecutionResult.__table__.constraints}
    assert "uq_controlled_receiver_delivery" in delivery_constraints
    assert "uq_controlled_receiver_nonce" in nonce_constraints
    assert "uq_delivery_execution_result_attempt" in result_constraints


def test_receiver_evidence_rejects_mutation():
    with pytest.raises(ValueError, match="append-only"):
        _reject_immutable_mutation()
