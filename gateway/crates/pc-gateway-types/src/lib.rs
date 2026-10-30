//! PR #2264 契约值类型。
//!
//! 网关无策略：这里的类型只承载 Core 的输入/输出，
//! 与 openapi/powercontext.yaml 对齐。

mod check;
mod prepare;

pub use check::*;
pub use prepare::*;
