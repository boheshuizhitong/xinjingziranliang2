//! 协议适配层：内部规范类型 ↔ 各服务商线格式。
//!
//! RFC 约束：只渲染获准的协议字段；保持角色、工具顺序、内容块、
//! 可复用边界与获准原生缓存设置；不向稳定 prompt 写入请求 ID/时间戳、
//! 不任意合并旧消息、不静默重映射目标。

mod canonical;
mod render;
mod sse;

pub use canonical::*;
pub use render::*;
pub use sse::*;
