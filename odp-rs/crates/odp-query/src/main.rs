//! ODP reconciliation query service.
//!
//! This service is the only ODP record read seam. It accepts an authenticated,
//! delegated, bounded reconciliation request from Admin and returns only
//! server-redacted record references.

mod query;
mod types;

use std::net::SocketAddr;

use anyhow::Context;
use axum::{
    extract::{State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use query::{machine_authorized, QueryService};
use serde_json::json;
use sqlx::postgres::PgPoolOptions;
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};
use types::{OdpQueryRequest, OdpQueryResponse, RequestError};

#[derive(Clone)]
struct AppState {
    service: QueryService,
    admin_machine_credential: String,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::registry()
        .with(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info,odp_query=debug".into()))
        .with(tracing_subscriber::fmt::layer())
        .init();

    let database_url = required_env("ODP_QUERY_DATABASE_URL")
        .or_else(|_| required_env("DATABASE_URL"))?;
    let admin_machine_credential = required_env("ODP_QUERY_ADMIN_CREDENTIAL")?;
    let cursor_secret = required_env("ODP_QUERY_CURSOR_SECRET")?;
    let pool = PgPoolOptions::new()
        .after_connect(|connection, _| {
            Box::pin(async move {
                sqlx::query("SET default_transaction_read_only = on")
                    .execute(connection)
                    .await?;
                Ok(())
            })
        })
        .connect(&database_url)
        .await
        .context("connect read-only odp-query pool")?;
    let state = AppState {
        service: QueryService::new(pool, cursor_secret.into_bytes())
            .map_err(|_| anyhow::anyhow!("ODP_QUERY_CURSOR_SECRET must be at least 32 bytes"))?,
        admin_machine_credential,
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/internal/v1/evidence-records:query", post(query))
        .with_state(state)
        .layer(TraceLayer::new_for_http());
    let host = std::env::var("ODP_QUERY_HOST").unwrap_or_else(|_| "0.0.0.0".into());
    let port: u16 = std::env::var("ODP_QUERY_PORT")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(8042);
    let address: SocketAddr = format!("{host}:{port}").parse()?;
    tracing::info!(%address, "odp-query starting");
    let listener = tokio::net::TcpListener::bind(address).await?;
    axum::serve(listener, app).await?;
    Ok(())
}

async fn health() -> Json<serde_json::Value> {
    Json(json!({"status": "ok", "service": "odp-query"}))
}

async fn query(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<OdpQueryRequest>,
) -> Result<Json<OdpQueryResponse>, QueryApiError> {
    if !machine_authorized(&headers, &state.admin_machine_credential) {
        return Err(QueryApiError(RequestError::Unauthorized));
    }
    state.service.execute(request).await.map(Json).map_err(QueryApiError)
}

fn required_env(name: &str) -> anyhow::Result<String> {
    let value = std::env::var(name).unwrap_or_default();
    if value.trim().is_empty() {
        anyhow::bail!("{name} is required")
    }
    Ok(value)
}

struct QueryApiError(RequestError);

impl IntoResponse for QueryApiError {
    fn into_response(self) -> Response {
        let (status, error) = match self.0 {
            RequestError::Unauthorized => (StatusCode::FORBIDDEN, "authorization failed"),
            RequestError::Unavailable => (StatusCode::SERVICE_UNAVAILABLE, "query unavailable"),
            RequestError::ResponseTooLarge => (StatusCode::PAYLOAD_TOO_LARGE, "request rejected"),
            RequestError::Invalid => (StatusCode::BAD_REQUEST, "request rejected"),
        };
        (status, Json(json!({"error": error}))).into_response()
    }
}
