//! Core 连接形态：UDS（同机组合部署）或 TCP（独立运行）。

use pc_gateway_core::{GateClient, GateError, HttpGateClient, UdsGateClient};
use pc_gateway_types::{
    CaptureContentSourceRequest, ContextCheckRequest, ContextCheckResult, PrepareContextRequest,
    PrepareContextResult,
};
use std::future::Future;

pub enum CoreLink {
    Uds(UdsGateClient),
    Http(HttpGateClient),
}

impl CoreLink {
    pub fn from_env() -> Self {
        if let Ok(sock) = std::env::var("PC_GATEWAY_CORE_UDS") {
            tracing::info!(%sock, "core link: UDS (combined deployment)");
            Self::Uds(UdsGateClient::new(sock))
        } else {
            let base =
                std::env::var("PC_GATEWAY_CORE_BASE").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
            tracing::info!(%base, "core link: TCP (standalone deployment)");
            Self::Http(HttpGateClient::new(base))
        }
    }
}

impl GateClient for CoreLink {
    fn check(
        &self,
        request: ContextCheckRequest,
    ) -> impl Future<Output = Result<ContextCheckResult, GateError>> + Send {
        async move {
            match self {
                CoreLink::Uds(c) => c.check(request).await,
                CoreLink::Http(c) => c.check(request).await,
            }
        }
    }

    fn capabilities(&self) -> impl Future<Output = Result<serde_json::Value, GateError>> + Send {
        async move {
            match self {
                CoreLink::Uds(c) => c.capabilities().await,
                CoreLink::Http(c) => c.capabilities().await,
            }
        }
    }

    fn prepare(
        &self,
        request: PrepareContextRequest,
    ) -> impl Future<Output = Result<PrepareContextResult, GateError>> + Send {
        async move {
            match self {
                CoreLink::Uds(c) => c.prepare(request).await,
                CoreLink::Http(c) => c.prepare(request).await,
            }
        }
    }

    fn capture(
        &self,
        request: CaptureContentSourceRequest,
    ) -> impl Future<Output = Result<serde_json::Value, GateError>> + Send {
        async move {
            match self {
                CoreLink::Uds(c) => c.capture(request).await,
                CoreLink::Http(c) => c.capture(request).await,
            }
        }
    }
}
