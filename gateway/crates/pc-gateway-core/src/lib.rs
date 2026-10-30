//! 执行器核心：一次托管调用的状态机。
//!
//! 对应 RFC「一次托管调用」时序图（PR #2199 两阶段检查形态）：
//!
//! ```text
//! 宿主完整输入 ─► check(before_send) ─┬─ allow ─► 发送 ─► 原始响应 ─► check(before_release) ─┬─ release ─► 返回
//!                                     ├─ withhold(渲染计划) ─► 只渲染获准字段 ─► 复检（最多一次）
//!                                     └─ block ──────────────────────────────────────────┴─ refuse ──► 显式拒绝
//! ```
//!
//! 网关无策略：每一步的裁决都来自 `GateClient`（check API 或嵌入式等价物），
//! 本 crate 只负责把裁决串成正确的控制流，并守住失败语义。

mod executor;
mod gate_client;
mod http_gate_client;
mod uds_gate_client;

pub use executor::*;
pub use gate_client::*;
pub use http_gate_client::*;
pub use uds_gate_client::*;
