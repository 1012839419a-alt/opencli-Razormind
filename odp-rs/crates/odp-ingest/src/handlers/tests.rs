use super::*;
use crate::dedup::DedupIndex;
use chrono::Utc;
use odp_contracts::{IngressOutcomeKindV1, IngressReceiptContextV1, IngestMode};
use std::sync::Arc;
use tokio::sync::{Mutex, RwLock};
use uuid::Uuid;

static SIGNATURE_ATTEMPT_TEST_LOCK: Mutex<()> = Mutex::const_new(());

fn sample_event(event_id: &str) -> RecordEvent {
    RecordEvent {
        schema_version: odp_contracts::SCHEMA_VERSION,
        provider: "rss/feed".into(),
        source_id: Uuid::new_v4(),
        event_id: event_id.into(),
        ingest_mode: IngestMode::Snapshot,
        source_ts: Utc::now(),
        cursor: None,
        payload: serde_json::json!({"title": "t"}),
        raw_data: serde_json::Value::Null,
        trace_id: None,
        task_id: None,
    }
}

fn state_without_bus() -> AppState {
    AppState {
        dedup: Arc::new(RwLock::new(DedupIndex::new())),
        bus: None,
    }
}

/// P0-2: with no bus configured (the ODP_INGEST_ALLOW_NO_BUS=1 opt-in dev
/// mode — main.rs refuses to start in this state otherwise), every event
/// must be rejected, NEVER accepted — an "accepted" count with no bus
/// would be a black hole: the event is not persisted anywhere.
#[tokio::test]
async fn process_events_with_no_bus_rejects_everything() {
    let state = state_without_bus();
    let events = vec![sample_event("e1"), sample_event("e2"), sample_event("e3")];

    let result = process_events(&state, events, false).await;

    assert_eq!(result.accepted, 0);
    assert_eq!(result.rejected, 3);
    assert_eq!(result.duplicates, 0);
    assert_eq!(result.errors.len(), 3);
    assert!(result.outcomes.is_empty());
    for e in &result.errors {
        assert!(e.reason.contains("no bus configured"));
    }
}

/// A duplicate event_id (same source_id/event_id already seen) must still
/// count as a duplicate, not a rejection, even with no bus — dedup runs
/// before the bus check.
#[tokio::test]
async fn process_events_with_no_bus_still_detects_duplicates() {
    let state = state_without_bus();
    let ev1 = sample_event("dup-1");
    // Same (source_id, event_id) as ev1 — the dedup key — so this is a
    // true duplicate of the first, not just a coincidentally-equal id.
    let ev2 = RecordEvent {
        source_id: ev1.source_id,
        ..sample_event("dup-1")
    };

    let result = process_events(&state, vec![ev1, ev2], false).await;

    assert_eq!(result.accepted, 0);
    assert_eq!(result.rejected, 1); // first one: rejected, no bus
    assert_eq!(result.duplicates, 1); // second one: same (source_id, event_id)
}

/// An invalid event must still be rejected for validation reasons, not
/// counted as a bus-related rejection — validation happens first.
#[tokio::test]
async fn process_events_validation_failure_before_bus_check() {
    let state = state_without_bus();
    let mut bad = sample_event("bad-1");
    bad.provider = String::new(); // fails RecordEvent::validate()

    let result = process_events(&state, vec![bad], false).await;

    assert_eq!(result.accepted, 0);
    assert_eq!(result.rejected, 1);
    assert!(!result.errors[0].reason.contains("no bus configured"));
}

#[tokio::test]
async fn governed_batch_over_bound_skips_processing_and_signing() {
    let _signature_lock = SIGNATURE_ATTEMPT_TEST_LOCK.lock().await;
    SIGNED_RECEIPT_ATTEMPTS.store(0, std::sync::atomic::Ordering::Relaxed);
    let state = state_without_bus();
    let events = (0..=MAX_GOVERNED_RECEIPT_OUTCOMES)
        .map(|index| sample_event(&format!("over-bound-{index}")))
        .collect();

    let (status, Json(result)) = ingest_batch(
        State(state.clone()),
        Json(IngestBatchRequest {
            events,
            receipt_context: Some(receipt_context()),
        }),
    )
    .await;

    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(result.rejected, MAX_GOVERNED_RECEIPT_OUTCOMES + 1);
    assert_eq!(result.errors.len(), 1);
    assert!(result.errors[0].reason.contains("governed receipt batch exceeds"));
    assert!(result.outcomes.is_empty());
    assert!(result.ingress_receipt.is_none());
    assert_eq!(state.dedup.read().await.len(), 0);
    assert_eq!(
        SIGNED_RECEIPT_ATTEMPTS.load(std::sync::atomic::Ordering::Relaxed),
        0
    );
}

fn receipt_context() -> IngressReceiptContextV1 {
    IngressReceiptContextV1 {
        workspace_id: "workspace".into(),
        project_id: "project".into(),
        workflow_id: "workflow".into(),
        studio_workflow_version_id: "version".into(),
        run_id: "run".into(),
        node_id: "node".into(),
        command_id: "command".into(),
        attempt_id: "attempt".into(),
        attempt_number: 1,
        task_id: "task".into(),
        trace_id: "trace".into(),
        source_id: "source".into(),
        source_binding_id: None,
        source_binding_revision_id: None,
        source_binding_revision_number: None,
        payload_sha256: "a".repeat(64),
        expected_key_set_sha256: "b".repeat(64),
    }
}

#[test]
fn signed_receipt_has_stable_identity_and_bounded_exact_outcomes() {
    let _signature_lock = SIGNATURE_ATTEMPT_TEST_LOCK.blocking_lock();
    std::env::set_var("ODP_INGRESS_RECEIPT_SECRET", "receipt-test-secret");
    let outcomes = vec![
        IngressOutcomeV1 {
            source_id: "source".into(),
            event_id: "accepted".into(),
            outcome: IngressOutcomeKindV1::Accepted,
            rejection_reason: None,
        },
        IngressOutcomeV1 {
            source_id: "source".into(),
            event_id: "duplicate".into(),
            outcome: IngressOutcomeKindV1::Duplicate,
            rejection_reason: None,
        },
        IngressOutcomeV1 {
            source_id: "source".into(),
            event_id: "rejected".into(),
            outcome: IngressOutcomeKindV1::Rejected,
            rejection_reason: Some("x".repeat(300)),
        },
    ];
    let first = signed_receipt(receipt_context(), outcomes.clone()).expect("signed receipt");
    let replay = signed_receipt(receipt_context(), outcomes).expect("signed receipt");
    assert!(
        signed_receipt(
            receipt_context(),
            vec![first.outcomes[0].clone(); MAX_GOVERNED_RECEIPT_OUTCOMES + 1],
        )
        .is_none()
    );
    std::env::remove_var("ODP_INGRESS_RECEIPT_SECRET");

    assert_eq!(first.receipt_id, replay.receipt_id);
    assert_eq!(first.idempotency_key, replay.idempotency_key);
    assert_eq!(first.producer_id, "odp-ingest");
    assert_eq!(first.receipt_hash.len(), 64);
    assert!(first.signature.starts_with("sha256="));
    assert_eq!(first.signature.len(), 71);
    assert_eq!(first.outcomes.len(), 3);
    assert!(matches!(first.outcomes[0].outcome, IngressOutcomeKindV1::Accepted));
    assert!(matches!(first.outcomes[1].outcome, IngressOutcomeKindV1::Duplicate));
    assert!(matches!(first.outcomes[2].outcome, IngressOutcomeKindV1::Rejected));
    assert_eq!(
        first.outcomes[2].rejection_reason.as_ref().unwrap().chars().count(),
        256
    );
    assert_eq!(first.issued_at.nanosecond() % 1_000, 0);
}
