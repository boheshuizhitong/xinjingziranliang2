//! 请求 ID：透传客户端的 X-PowerContext-Request-ID 或生成新 ID，
//! 注入请求扩展（供 handler/日志取用）并回写到响应头。
//! 对齐 PC 的 HttpRequestIdMiddleware，贯通排障链路。

use super::{GatewayMiddleware, REQUEST_ID_HEADER};
use axum::{extract::Request, middleware::Next, response::Response};
use std::future::Future;
use std::pin::Pin;
use std::sync::atomic::{AtomicU64, Ordering};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

pub struct RequestId;

fn generate() -> String {
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    let seq = SEQUENCE.fetch_add(1, Ordering::Relaxed);
    format!("gw-{ts:x}-{seq:06x}")
}

impl GatewayMiddleware for RequestId {
    fn name(&self) -> &'static str {
        "request_id"
    }

    fn handle<'a>(
        &'a self,
        mut req: Request,
        next: Next,
    ) -> Pin<Box<dyn Future<Output = Response> + Send + 'a>> {
        Box::pin(async move {
        let id = req
            .headers()
            .get(&REQUEST_ID_HEADER)
            .and_then(|v| v.to_str().ok())
            .filter(|v| !v.is_empty() && v.len() <= 128 && v.chars().all(|c| c.is_ascii_graphic()))
            .map(|v| v.to_string())
            .unwrap_or_else(generate);
        // 注入扩展 + 当前 span，供后续 handler 与日志关联。
        req.extensions_mut().insert(id.clone());
        tracing::Span::current().record("request_id", &id);
        let mut resp = next.run(req).await;
        if resp.headers().get(&REQUEST_ID_HEADER).is_none() {
            if let Ok(v) = axum::http::HeaderValue::from_str(&id) {
                resp.headers_mut().insert(REQUEST_ID_HEADER, v);
            }
        }
        resp
        })
    }
}
