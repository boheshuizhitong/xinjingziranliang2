/**
 * Embedder: 浏览器端向量化封装
 *
 * 关键设计:
 *  - 模型: Xenova/all-MiniLM-L6-v2 (dim=384)
 *  - device 选择: WebGPU → WASM 自动降级
 *  - 量化: 可切换 int8 量化版本 (体积更小, 精度略降)
 *  - 批处理: pipeline 默认支持数组输入, 一次 forward N 条
 *
 * 注意: 所有计算在浏览器本地完成, 不调用任何云端 embedding API.
 */

import { pipeline, env } from '@huggingface/transformers';

// 禁用本地模型探测, 强制从 HF Hub 拉 (首次会下载 ~22MB)
env.allowLocalModels = false;
// 允许使用浏览器上较新的 WASM SIMD/线程特性
env.useBrowserCache = true;

// 默认模型
export const MODEL_NAME_FP32 = 'Xenova/all-MiniLM-L6-v2';
export const MODEL_NAME_INT8 = 'Xenova/all-MiniLM-L6-v2'; // HF 默认 int8 ONNX 在子目录, 下面自动切换

export const EMBEDDING_DIM = 384;

let cachedPipeline = null;
let cachedDevice = null;
let cachedDtype = null;

/**
 * 检测当前浏览器可用的推理后端
 */
export function detectBackend() {
  const hasWebGPU = typeof navigator !== 'undefined' && !!navigator.gpu;
  const hasWebGL = typeof WebGLRenderingContext !== 'undefined';
  // WASM 始终可用
  return {
    webgpu: hasWebGPU,
    webgl: hasWebGL,
    wasm: true, // 兜底
    recommendedDevice: hasWebGPU ? 'webgpu' : 'wasm',
  };
}

/**
 * 动态构造模型 ID: 量化模型放在 HF Hub 的 quantized 子目录下
 */
function resolveModelId(baseModel, quantized) {
  // Xenova 用户下的量化版本通常在: Xenova/all-MiniLM-L6-v2 / int8 / onnx
  // Transformers.js v3 支持通过 quantized 参数让它自己拼 path
  return baseModel;
}

/**
 * 加载 embedding pipeline. 只加载一次, 之后复用.
 *
 * @param {'auto'|'webgpu'|'wasm'} device
 * @param {'fp32'|'int8'} dtype
 * @param {(stage:string, info?:any)=>void} onProgress  进度回调
 */
export async function getEmbedder({
  device = 'auto',
  dtype = 'fp32',
  onProgress = () => {},
} = {}) {
  // device 解析: auto → 检测 WebGPU
  let resolvedDevice = device;
  if (resolvedDevice === 'auto') {
    const { recommendedDevice } = detectBackend();
    resolvedDevice = recommendedDevice;
  }
  // 如果用户显式要求 webgpu 但浏览器不支持, 自动降级
  if (resolvedDevice === 'webgpu' && !detectBackend().webgpu) {
    console.warn('[embedder] WebGPU 不可用, 降级到 WASM');
    resolvedDevice = 'wasm';
  }

  // 命中缓存
  if (cachedPipeline && cachedDevice === resolvedDevice && cachedDtype === dtype) {
    return cachedPipeline;
  }

  onProgress('loading', { device: resolvedDevice, dtype });

  const modelId = dtype === 'int8'
    ? 'Xenova/all-MiniLM-L6-v2'   // Transformers.js 会自动加载 quantized int8 onnx
    : 'Xenova/all-MiniLM-L6-v2';

  // pipeline('feature-extraction') 返回的 pooler 输出即为句向量
  cachedPipeline = await pipeline('feature-extraction', modelId, {
    quantized: dtype === 'int8',
    device: resolvedDevice,
    dtype: dtype === 'int8' ? 'q8' : 'fp32',
    progress_callback: (info) => {
      // Transformers.js 内部下载/构建进度
      onProgress('model-download', info);
    },
  });

  cachedDevice = resolvedDevice;
  cachedDtype = dtype;
  onProgress('ready', { device: resolvedDevice, dtype });

  return cachedPipeline;
}

/**
 * 生成单条文本的向量
 */
export async function embedOne(text, embedder) {
  const out = await embedder(text, { pooling: 'mean', normalize: true });
  return Array.from(out.data);
}

/**
 * 批量生成向量. Transformers.js 的 pipeline 直接吃数组, 一次 forward 搞定.
 *
 * @param {string[]} texts
 * @param embedder
 * @param {(done:number,total:number)} onChunk  每处理一批回调
 * @param {number} batchSize  批大小. 端侧建议 8-16, 过大可能 OOM.
 * @returns {Promise<number[][]>} 与 texts 一一对应的向量数组
 */
export async function embedBatch(texts, embedder, { batchSize = 16, onChunk } = {}) {
  if (!texts.length) return [];

  const results = new Array(texts.length);
  let done = 0;

  for (let i = 0; i < texts.length; i += batchSize) {
    const chunk = texts.slice(i, i + batchSize);
    // Transformers.js v3 直接用 batch_inputs
    const out = await embedder(chunk, { pooling: 'mean', normalize: true });
    // out.data 是扁平 Float32Array; 每条 EMBEDDING_DIM 个 float
    const flat = out.data;
    for (let j = 0; j < chunk.length; j++) {
      const vec = new Array(EMBEDDING_DIM);
      const offset = j * EMBEDDING_DIM;
      for (let k = 0; k < EMBEDDING_DIM; k++) vec[k] = flat[offset + k];
      results[i + j] = vec;
    }
    done += chunk.length;
    onChunk?.(done, texts.length);
  }
  return results;
}

/**
 * 简单的文本分块器 (中文也友好)
 * 策略: 按段落 → 超长段落再按句切 → chunk_size tokens, overlap 滑窗
 * 这里用"字符数"近似 token, 避免再跑 tokenizer (省一次加载).
 */
export function chunkText(text, { chunkChars = 500, overlapChars = 80 } = {}) {
  if (!text) return [];
  // 先合并换行, 保留段落
  const paragraphs = text
    .replace(/\r\n/g, '\n')
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);

  const chunks = [];
  let buf = '';
  for (const para of paragraphs) {
    if (buf.length + para.length + 2 <= chunkChars) {
      buf = buf ? `${buf}\n\n${para}` : para;
    } else {
      if (buf) { chunks.push(buf); buf = ''; }
      // 长段落切片
      if (para.length <= chunkChars) {
        buf = para;
      } else {
        let i = 0;
        while (i < para.length) {
          const end = Math.min(para.length, i + chunkChars);
          chunks.push(para.slice(i, end));
          i += chunkChars - overlapChars;
        }
      }
    }
  }
  if (buf) chunks.push(buf);
  return chunks.filter((c) => c.trim().length > 20);
}

export function getCachedDevice() { return cachedDevice; }
export function getCachedDtype() { return cachedDtype; }
