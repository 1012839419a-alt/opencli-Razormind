use axum::{
    body::Bytes,
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use chrono::{Timelike, Utc};
use hmac::{Hmac, Mac};
use odp_contracts::{
    IngestBatchRequest, IngestBatchResponse, IngestReject, IngressOutcomeKindV1, IngressOutcomeV1,
    ODPIngressOutcomeReceiptV1, RecordEvent,
};
use serde_json::json;
use sha2::{Digest, Sha256};
use crate::state::AppState;

pub async fn health() -> impl IntoResponse {
    Json(json!({
        "status": "ok",
        "service": "odp-ingest",
        "schema_version": odp_contracts::SCHEMA_VERSION
    }))
}

pub async fn ingest_batch(
    State(state): State<AppState>,
    Json(body): Json<IngestBatchRequest>,
) -> impl IntoResponse {
    let IngestBatchRequest {
        events,
        receipt_context,
    } = body;
    let mut result = process_events(&state, events).await;
    if let Some(context) = receipt_context {
        result.ingress_receipt = signed_receipt(context, &result.outcomes);
    }
    (StatusCode::ACCEPTED, Json(result))
}

/// NDJSON: one RecordEvent per line (high-throughput clients).
pub async fn ingest_ndjson(
    State(state): State<AppState>,
    body: Bytes,
) -> impl IntoResponse {
    let mut events = Vec::new();
    let text = String::from_utf8_lossy(&body);
    for (i, line) in text.lines().enumerate() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        match serde_json::from_str::<RecordEvent>(line) {
            Ok(ev) => events.push(ev),
            Err(e) => {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(IngestBatchResponse {
                        accepted: 0,
                        duplicates: 0,
                        rejected: 1,
                        errors: vec![IngestReject {
                            index: i,
                            event_id: None,
                            reason: e.to_string(),
                        }],
                        outcomes: vec![],
                        ingress_receipt: None,
                    }),
                )
                    .into_response();
            }
        }
    }
    let result = process_events(&state, events).await;
    (StatusCode::ACCEPTED, Json(result)).into_response()
}

async fn process_events(state: &AppState, events: Vec<RecordEvent>) -> IngestBatchResponse {
    let mut accepted = 0usize;
    let mut duplicates = 0usize;
    let mut rejected = 0usize;
    let mut errors = Vec::new();
    let mut outcomes = Vec::new();
    let mut dedup = state.dedup.write().await;

    for (index, event) in events.into_iter().enumerate() {
        let source_id = event.source_id.to_string();
        let event_id = event.event_id.clone();
        if let Err(e) = event.validate() {
            let reason = bounded_reason(e.to_string());
            rejected += 1;
            errors.push(IngestReject {
                index,
                event_id: Some(event_id.clone()),
                reason: reason.clone(),
            });
            outcomes.push(IngressOutcomeV1 {
                source_id,
                event_id,
                outcome: IngressOutcomeKindV1::Rejected,
                rejection_reason: Some(reason),
            });
            continue;
        }

        let (dedup_source_id, dedup_event_id) = event.idempotency_key();
        if dedup.try_insert(dedup_source_id, dedup_event_id.to_string()) {
            if let Some(bus) = &state.bus {
                match bus.publish_ingest(&event).await {
                    Ok(_) => {
                        accepted += 1;
                        outcomes.push(IngressOutcomeV1 {
                            source_id,
                            event_id,
                            outcome: IngressOutcomeKindV1::Accepted,
                            rejection_reason: None,
                        });
                    }
                    Err(e) => {
                        let reason = bounded_reason(format!("bus publish failed: {e}"));
                        rejected += 1;
                        dedup.remove(dedup_source_id, dedup_event_id);
                        errors.push(IngestReject {
                            index,
                            event_id: Some(event_id.clone()),
                            reason: reason.clone(),
                        });
                        outcomes.push(IngressOutcomeV1 {
                            source_id,
                            event_id,
                            outcome: IngressOutcomeKindV1::Rejected,
                            rejection_reason: Some(reason),
                        });
                    }
                }
            } else {
                let reason = "no bus configured; event not persisted".to_string();
                rejected += 1;
                errors.push(IngestReject {
                    index,
                    event_id: Some(event_id.clone()),
                    reason: reason.clone(),
                });
                outcomes.push(IngressOutcomeV1 {
                    source_id,
                    event_id,
                    outcome: IngressOutcomeKindV1::Rejected,
                    rejection_reason: Some(reason),
                });
            }
        } else {
            duplicates += 1;
            outcomes.push(IngressOutcomeV1 {
                source_id,
                event_id,
                outcome: IngressOutcomeKindV1::Duplicate,
                rejection_reason: None,
            });
        }
    }

    IngestBatchResponse {
        accepted,
        duplicates,
        rejected,
        errors,
        outcomes,
        ingress_receipt: None,
    }
}

fn bounded_reason(reason: String) -> String {
    reason.chars().take(256).collect()
}

fn signed_receipt(
    context: odp_contracts::IngressReceiptContextV1,
    outcomes: &[IngressOutcomeV1],
) -> Option<ODPIngressOutcomeReceiptV1> {
    if outcomes.len() > 1000 {
        return None;
    }
    let secret = std::env::var("ODP_INGRESS_RECEIPT_SECRET").ok().filter(|value| !value.is_empty())?;
    let outcomes: Vec<_> = outcomes
        .iter()
        .cloned()
        .map(|mut outcome| {
            outcome.rejection_reason = outcome.rejection_reason.map(bounded_reason);
            outcome
        })
        .collect();
    let identity = serde_json::to_vec(&(&context, &outcomes)).ok()?;
    let idempotency_key = hex_sha256(&identity);
    let now = Utc::now();
    let issued_at = now
        .with_nanosecond(now.nanosecond() / 1_000 * 1_000)
        .expect("nanosecond truncation remains valid");
    let mut receipt = ODPIngressOutcomeReceiptV1 {
        version: "v1".to_string(),
        receipt_id: format!("odp-ingest:{idempotency_key}"),
        idempotency_key: format!("odp-ingest:{idempotency_key}"),
        producer_id: "odp-ingest".to_string(),
        producer_key_id: std::env::var("ODP_INGRESS_RECEIPT_KEY_ID")
            .unwrap_or_else(|_| "odp-ingest-v1".to_string()),
        context,
        outcomes,
        issued_at,
        receipt_hash: String::new(),
        signature: String::new(),
    };
    let canonical = serde_json::to_vec(&serde_json::json!({
        "version": &receipt.version,
        "receipt_id": &receipt.receipt_id,
        "idempotency_key": &receipt.idempotency_key,
        "producer_id": &receipt.producer_id,
        "producer_key_id": &receipt.producer_key_id,
        "workspace_id": &receipt.context.workspace_id,
        "project_id": &receipt.context.project_id,
        "workflow_id": &receipt.context.workflow_id,
        "studio_workflow_version_id": &receipt.context.studio_workflow_version_id,
        "run_id": &receipt.context.run_id,
        "node_id": &receipt.context.node_id,
        "command_id": &receipt.context.command_id,
        "attempt_id": &receipt.context.attempt_id,
        "attempt_number": receipt.context.attempt_number,
        "task_id": &receipt.context.task_id,
        "trace_id": &receipt.context.trace_id,
        "source_id": &receipt.context.source_id,
        "source_binding_id": &receipt.context.source_binding_id,
        "source_binding_revision_id": &receipt.context.source_binding_revision_id,
        "source_binding_revision_number": receipt.context.source_binding_revision_number,
        "payload_sha256": &receipt.context.payload_sha256,
        "expected_key_set_sha256": &receipt.context.expected_key_set_sha256,
        "outcomes": &receipt.outcomes,
        "issued_at": &receipt.issued_at,
    })).ok()?;
    receipt.receipt_hash = hex_sha256(&canonical);
    let mut mac = Hmac::<Sha256>::new_from_slice(secret.as_bytes()).ok()?;
    mac.update(receipt.receipt_hash.as_bytes());
    receipt.signature = format!("sha256={:x}", mac.finalize().into_bytes());
    Some(receipt)
}

fn hex_sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::dedup::DedupIndex;
    use chrono::Utc;
    use odp_contracts::{IngressOutcomeKindV1, IngressReceiptContextV1, IngestMode};
    use std::sync::Arc;
    use tokio::sync::RwLock;
    use uuid::Uuid;

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
        let events = vec![
            sample_event("e1"),
            sample_event("e2"),
            sample_event("e3"),
        ];

        let result = process_events(&state, events).await;

        assert_eq!(result.accepted, 0);
        assert_eq!(result.rejected, 3);
        assert_eq!(result.duplicates, 0);
        assert_eq!(result.errors.len(), 3);
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

        let result = process_events(&state, vec![ev1, ev2]).await;

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

        let result = process_events(&state, vec![bad]).await;

        assert_eq!(result.accepted, 0);
        assert_eq!(result.rejected, 1);
        assert!(!result.errors[0].reason.contains("no bus configured"));
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
        let first = signed_receipt(receipt_context(), &outcomes).expect("signed receipt");
        let replay = signed_receipt(receipt_context(), &outcomes).expect("signed receipt");
        assert!(signed_receipt(receipt_context(), &vec![outcomes[0].clone(); 1001]).is_none());
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
        assert_eq!(first.outcomes[2].rejection_reason.as_ref().unwrap().chars().count(), 256);
        assert_eq!(first.issued_at.nanosecond() % 1_000, 0);
    }
}