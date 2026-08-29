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

const MAX_GOVERNED_RECEIPT_OUTCOMES: usize = 1_000;

#[cfg(test)]
static SIGNED_RECEIPT_ATTEMPTS: std::sync::atomic::AtomicUsize =
    std::sync::atomic::AtomicUsize::new(0);

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
) -> (StatusCode, Json<IngestBatchResponse>) {
    let IngestBatchRequest {
        events,
        receipt_context,
    } = body;
    let (status, result) = match receipt_context {
        Some(_) if events.len() > MAX_GOVERNED_RECEIPT_OUTCOMES => (
            StatusCode::BAD_REQUEST,
            governed_batch_limit_response(events.len()),
        ),
        Some(context) => {
            let mut result = process_events(&state, events, true).await;
            result.ingress_receipt = signed_receipt(context, std::mem::take(&mut result.outcomes));
            (StatusCode::ACCEPTED, result)
        }
        None => (StatusCode::ACCEPTED, process_events(&state, events, false).await),
    };
    (status, Json(result))
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
    let result = process_events(&state, events, false).await;
    (StatusCode::ACCEPTED, Json(result)).into_response()
}

async fn process_events(
    state: &AppState,
    events: Vec<RecordEvent>,
    capture_outcomes: bool,
) -> IngestBatchResponse {
    let mut accepted = 0usize;
    let mut duplicates = 0usize;
    let mut rejected = 0usize;
    let mut errors = Vec::new();
    let mut outcomes = capture_outcomes.then(Vec::new);
    let mut dedup = state.dedup.write().await;

    for (index, event) in events.into_iter().enumerate() {
        if let Err(e) = event.validate() {
            let reason = bounded_reason(e.to_string());
            rejected += 1;
            if let Some(outcomes) = outcomes.as_mut() {
                let source_id = event.source_id.to_string();
                let event_id = event.event_id;
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
            } else {
                errors.push(IngestReject {
                    index,
                    event_id: Some(event.event_id),
                    reason,
                });
            }
            continue;
        }

        let (dedup_source_id, dedup_event_id) = event.idempotency_key();
        if dedup.try_insert(dedup_source_id, dedup_event_id.to_string()) {
            if let Some(bus) = &state.bus {
                match bus.publish_ingest(&event).await {
                    Ok(_) => {
                        accepted += 1;
                        if let Some(outcomes) = outcomes.as_mut() {
                            outcomes.push(IngressOutcomeV1 {
                                source_id: event.source_id.to_string(),
                                event_id: event.event_id,
                                outcome: IngressOutcomeKindV1::Accepted,
                                rejection_reason: None,
                            });
                        }
                    }
                    Err(e) => {
                        let reason = bounded_reason(format!("bus publish failed: {e}"));
                        rejected += 1;
                        dedup.remove(dedup_source_id, dedup_event_id);
                        if let Some(outcomes) = outcomes.as_mut() {
                            let event_id = event.event_id.clone();
                            errors.push(IngestReject {
                                index,
                                event_id: Some(event_id.clone()),
                                reason: reason.clone(),
                            });
                            outcomes.push(IngressOutcomeV1 {
                                source_id: event.source_id.to_string(),
                                event_id,
                                outcome: IngressOutcomeKindV1::Rejected,
                                rejection_reason: Some(reason),
                            });
                        } else {
                            errors.push(IngestReject {
                                index,
                                event_id: Some(event.event_id),
                                reason,
                            });
                        }
                    }
                }
            } else {
                let reason = "no bus configured; event not persisted".to_string();
                rejected += 1;
                if let Some(outcomes) = outcomes.as_mut() {
                    let event_id = event.event_id.clone();
                    errors.push(IngestReject {
                        index,
                        event_id: Some(event_id.clone()),
                        reason: reason.clone(),
                    });
                    outcomes.push(IngressOutcomeV1 {
                        source_id: event.source_id.to_string(),
                        event_id,
                        outcome: IngressOutcomeKindV1::Rejected,
                        rejection_reason: Some(reason),
                    });
                } else {
                    errors.push(IngestReject {
                        index,
                        event_id: Some(event.event_id),
                        reason,
                    });
                }
            }
        } else {
            duplicates += 1;
            if let Some(outcomes) = outcomes.as_mut() {
                outcomes.push(IngressOutcomeV1 {
                    source_id: event.source_id.to_string(),
                    event_id: event.event_id,
                    outcome: IngressOutcomeKindV1::Duplicate,
                    rejection_reason: None,
                });
            }
        }
    }

    IngestBatchResponse {
        accepted,
        duplicates,
        rejected,
        errors,
        outcomes: outcomes.unwrap_or_default(),
        ingress_receipt: None,
    }
}

fn governed_batch_limit_response(events_len: usize) -> IngestBatchResponse {
    IngestBatchResponse {
        accepted: 0,
        duplicates: 0,
        rejected: events_len,
        errors: vec![IngestReject {
            index: 0,
            event_id: None,
            reason: format!(
                "governed receipt batch exceeds the {MAX_GOVERNED_RECEIPT_OUTCOMES}-event bound"
            ),
        }],
        outcomes: vec![],
        ingress_receipt: None,
    }
}

fn bounded_reason(reason: String) -> String {
    reason.chars().take(256).collect()
}

fn signed_receipt(
    context: odp_contracts::IngressReceiptContextV1,
    mut outcomes: Vec<IngressOutcomeV1>,
) -> Option<ODPIngressOutcomeReceiptV1> {
    #[cfg(test)]
    SIGNED_RECEIPT_ATTEMPTS.fetch_add(1, std::sync::atomic::Ordering::Relaxed);

    if outcomes.len() > MAX_GOVERNED_RECEIPT_OUTCOMES {
        return None;
    }
    let secret = std::env::var("ODP_INGRESS_RECEIPT_SECRET").ok().filter(|value| !value.is_empty())?;
    for outcome in &mut outcomes {
        outcome.rejection_reason = outcome.rejection_reason.take().map(bounded_reason);
    }
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
mod tests;