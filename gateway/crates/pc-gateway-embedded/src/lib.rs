//! 嵌入式路径的占位 crate。
//!
//! RFC：SDK/内置执行与 Rust GatewayRuntime 是按调用配置的两种执行路径，
//! 同一部署可并存，落实同一套 Core 决策。本 crate 未来承载
//! pyo3/FFI 绑定，让 Python 进程内执行器复用 `pc-gateway-core` 的状态机，
//! 并以进程内 `GateClient` 实现直调 Core 算法（无需 HTTP）。
//!
//! v1 尚未实现；保留 crate 以固定 workspace 边界。
