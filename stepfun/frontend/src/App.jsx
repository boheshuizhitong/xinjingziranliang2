import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api.js';
import {
  detectBackend,
  getEmbedder,
  embedBatch,
  embedOne,
  chunkText,
  EMBEDDING_DIM,
  getCachedDevice,
  getCachedDtype,
} from './embedder.js';

/* ============================================================
 * App: 端侧知识库主界面
 * ============================================================ */
export default function App() {
  // ---------- 基础状态 ----------
  const backendInfo = detectBackend();
  const [health, setHealth] = useState(null);
  const [device, setDevice] = useState('auto');      // auto | webgpu | wasm
  const [dtype, setDtype] = useState('fp32');         // fp32 | int8
  const [collection, setCollection] = useState('seekdb_knowledge_base');
  const [collections, setCollections] = useState([]);

  // ---------- 模型 / 文档 ----------
  const [embedder, setEmbedder] = useState(null);
  const [modelStatus, setModelStatus] = useState('idle'); // idle | loading | ready | error
  const [modelProgress, setModelProgress] = useState(null);

  const [files, setFiles] = useState([]);            // 待导入文件列表
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState({ done: 0, total: 0, phase: '' });
  const [chunks, setChunks] = useState([]);          // 分块预览 (来自所有文件)

  // ---------- 检索 ----------
  const [queryText, setQueryText] = useState('');
  const [activeTab, setActiveTab] = useState('hybrid'); // hybrid | vector | text
  const [results, setResults] = useState({ hybrid: null, vector: null, text: null });
  const [searching, setSearching] = useState(false);

  // refs
  const fileRef = useRef(null);

  // ---------- 性能计时 ----------
  const [metrics, setMetrics] = useState({
    modelLoadMs: null,
    embedMs: null,
    embedThroughput: null,   // docs/s
    writeMs: null,
    queryEmbedMs: null,
    searchMs: null,
    e2eMs: null,
  });

  // ---------- 生命周期 ----------
  useEffect(() => {
    api.health()
      .then((h) => { setHealth(h); return api.listCollections(); })
      .then((list) => {
        setCollections(list.collections || []);
      })
      .catch((e) => {
        console.warn('后端未就绪:', e.message);
        setHealth({ ok: false });
      });
  }, []);

  // ---------- 加载模型 ----------
  const loadModel = useCallback(async () => {
    setModelStatus('loading');
    setModelProgress(null);
    const t0 = performance.now();
    try {
      const em = await getEmbedder({
        device,
        dtype,
        onProgress: (stage, info) => {
          setModelProgress({ stage, info });
          if (stage === 'model-download' && info?.progress != null) {
            setModelProgress((p) => ({ ...p, percent: info.progress }));
          }
        },
      });
      const t1 = performance.now();
      setEmbedder(em);
      setModelStatus('ready');
      setMetrics((m) => ({ ...m, modelLoadMs: +(t1 - t0).toFixed(1) }));
    } catch (e) {
      console.error(e);
      setModelStatus('error');
      setModelProgress({ error: e.message });
    }
  }, [device, dtype]);

  // ---------- 文件处理 ----------
  const onFileInput = (e) => handleFiles(Array.from(e.target.files));
  const onDrop = (e) => {
    e.preventDefault();
    handleFiles(Array.from(e.dataTransfer.files));
  };
  const handleFiles = (fileList) => {
    setFiles((prev) => [...prev, ...fileList.map((f) => ({ file: f, id: crypto.randomUUID() }))]);
  };

  // 把待导入文件读入内容并分块
  const readFilesAndChunk = async () => {
    const allChunks = [];
    for (const { file, id } of files) {
      const text = await file.text();
      const parts = chunkText(text);
      parts.forEach((content, i) => {
        allChunks.push({
          id: `${id}_c${i}`,
          document: content,
          metadata: { source: file.name, chunkIndex: i },
        });
      });
    }
    return allChunks;
  };

  // ---------- 一键导入 (分阶段计时) ----------
  const runImport = async () => {
    if (!embedder) { alert('请先加载模型'); return; }
    if (!files.length) { alert('请先选择文件'); return; }
    setImporting(true);
    try {
      // phase 1: 读文件 + 分块
      setImportProgress({ phase: '读取文件并分块', done: 0, total: 1 });
      const readStart = performance.now();
      const allChunks = await readFilesAndChunk();
      setChunks(allChunks);
      setImportProgress({ phase: '读取文件并分块', done: 1, total: 1, detail: `${allChunks.length} 个 chunk` });

      // phase 2: embedding (批处理)
      setImportProgress({ phase: '浏览器端向量化', done: 0, total: allChunks.length });
      const texts = allChunks.map((c) => c.document);
      const embedStart = performance.now();
      const vectors = await embedBatch(texts, embedder, {
        batchSize: 16,
        onChunk: (done, total) => setImportProgress({
          phase: '浏览器端向量化', done, total,
        }),
      });
      const embedEnd = performance.now();
      const embedMs = +(embedEnd - embedStart).toFixed(1);
      const throughput = +(allChunks.length / (embedMs / 1000)).toFixed(1);
      setMetrics((m) => ({ ...m, embedMs, embedThroughput: throughput }));

      // phase 3: 写入 seekdb + 索引刷新
      setImportProgress({ phase: '写入 seekdb', done: 0, total: allChunks.length });
      const batch = allChunks.map((c, i) => ({
        id: c.id,
        document: c.document,
        vector: vectors[i],
        metadata: c.metadata,
      }));
      const writeStart = performance.now();
      await api.documents(collection, batch);
      const writeEnd = performance.now();
      setMetrics((m) => ({ ...m, writeMs: +(writeEnd - writeStart).toFixed(1) }));
      setImportProgress({ phase: '完成', done: allChunks.length, total: allChunks.length });

      // 刷新 collection 列表
      try {
        const list = await api.listCollections();
        setCollections(list.collections || []);
      } catch {}

      setImportProgress({ phase: '已完成 ✓', done: allChunks.length, total: allChunks.length });
    } catch (e) {
      console.error(e);
      alert('导入失败: ' + e.message);
    } finally {
      setImporting(false);
    }
  };

  // ---------- 检索 ----------
  const runSearch = async () => {
    if (!embedder) { alert('请先加载模型'); return; }
    if (!queryText.trim()) { alert('请输入查询'); return; }
    setSearching(true);
    const t0 = performance.now();
    try {
      const qStart = performance.now();
      const qvec = await embedOne(queryText, embedder);
      const qEnd = performance.now();
      setMetrics((m) => ({ ...m, queryEmbedMs: +(qEnd - qStart).toFixed(1) }));

      const textPresent = queryText.trim().length > 0;

      const [hybridR, vectorR, textR] = await Promise.all([
        // hybridSearch: 全文 + 向量 + RRF
        api.search({
          collection, queryText: textPresent ? queryText : '', queryVector: qvec, nResults: 10,
        }).catch((e) => ({ ok: false, error: e.message })),
        // 纯向量 (对比)
        api.searchVector(collection, qvec, 10).catch((e) => ({ ok: false, error: e.message })),
        // 纯全文 (对比)
        textPresent ? api.searchText(collection, queryText, 10).catch((e) => ({ ok: false, error: e.message })) : { ok: true, results: [] },
      ]);

      const t1 = performance.now();
      setResults({
        hybrid: hybridR,
        vector: vectorR,
        text: textR,
      });
      setMetrics((m) => ({
        ...m,
        searchMs: +((hybridR.searchMs ?? 0) + (vectorR.searchMs ?? 0) + (textR.searchMs ?? 0)).toFixed(1),
        e2eMs: +(t1 - t0).toFixed(1),
      }));
    } catch (e) {
      alert('检索失败: ' + e.message);
    } finally {
      setSearching(false);
    }
  };

  // ---------- 渲染辅助 ----------
  const effectiveDevice = modelStatus === 'ready' ? getCachedDevice() : (device === 'auto' ? backendInfo.recommendedDevice : device);
  const effectiveDtype = modelStatus === 'ready' ? getCachedDtype() : dtype;

  const renderStatusBadge = () => {
    if (!health?.ok) return <span className="badge err">后端未连接</span>;
    const parts = [];
    parts.push(<span key="db" className="badge ok">后端已连接</span>);
    parts.push(<span key="dim" className="badge info">dim={EMBEDDING_DIM}</span>);
    const devColor = effectiveDevice === 'webgpu' ? 'ok' : (effectiveDevice === 'webgl' ? 'info' : 'warn');
    parts.push(<span key="dev" className={`badge ${devColor}`}>推理: {effectiveDevice}</span>);
    parts.push(<span key="dt" className="badge">精度: {effectiveDtype}</span>);
    return parts;
  };

  const resultRows = results[activeTab]?.results ?? [];
  const tabData = {
    hybrid: { label: 'Hybrid 混合检索', data: results.hybrid },
    vector: { label: 'Vector 纯向量检索', data: results.vector },
    text:   { label: 'Text 纯全文检索', data: results.text },
  };

  return (
    <div className="app">
      {/* ============ 顶部 Header ============ */}
      <header className="header wide">
        <div>
          <h1>🔎 seekdb × Transformers.js · 端侧知识库</h1>
          <div className="small muted">浏览器本地向量化 · seekdb 混合检索 (RRF 融合) · no cloud</div>
        </div>
        <div className="status-bar">
          {renderStatusBadge()}
          <select
            value={device}
            onChange={(e) => setDevice(e.target.value)}
            title="推理后端选择"
          >
            <option value="auto">auto (自动)</option>
            <option value="webgpu">WebGPU {backendInfo.webgpu ? '✓' : '(不可用)'}</option>
            <option value="wasm">WASM</option>
          </select>
          <select
            value={dtype}
            onChange={(e) => setDtype(e.target.value)}
            title="量化精度"
          >
            <option value="fp32">FP32</option>
            <option value="int8">INT8 量化</option>
          </select>
          <button className="primary" onClick={loadModel} disabled={modelStatus === 'loading'}>
            {modelStatus === 'ready' ? '重新加载模型' : '加载模型'}
          </button>
        </div>
      </header>

      {/* ============ 左侧: 文档导入 + 进度 ============ */}
      <section className="panel">
        <h2>📄 文档导入 <small>→ 浏览器端向量化 → seekdb 写入</small></h2>

        {/* 模型状态 */}
        {modelStatus === 'idle' && (
          <div className="small muted">请先在顶部选择推理后端并加载模型。</div>
        )}
        {modelStatus === 'loading' && (
          <div>
            <div className="small muted">⏳ 加载模型中… {modelProgress?.stage || ''}</div>
            {modelProgress?.percent != null && (
              <div className="progress"><div className="progress-bar" style={{ width: modelProgress.percent + '%' }} /></div>
            )}
          </div>
        )}
        {modelStatus === 'ready' && (
          <div className="small muted">✓ 模型已就绪 · device={getCachedDevice()} · dtype={getCachedDtype()}</div>
        )}
        {modelStatus === 'error' && (
          <div className="small" style={{ color: '#f53f3f' }}>加载失败: {modelProgress?.error}</div>
        )}

        {/* 选择 collection */}
        <div className="row" style={{ marginTop: 12 }}>
          <label className="small muted" style={{ minWidth: 90 }}>Collection:</label>
          <input
            type="text"
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
            style={{ flex: 1 }}
          />
          <button
            onClick={async () => {
              await api.createCollection(collection, EMBEDDING_DIM);
              setCollections((cs) => [...new Set([...cs, collection])]);
            }}
            disabled={!collection}
          >创建</button>
          <button
            className="danger"
            onClick={async () => {
              if (confirm(`确认删除 collection "${collection}"?`)) {
                await api.deleteCollection(collection);
                setCollections((cs) => cs.filter((c) => c !== collection));
              }
            }}
            disabled={!collection}
          >删除</button>
        </div>
        {collections.length > 0 && (
          <div className="small muted" style={{ marginTop: 4 }}>
            已有集合: {collections.join(', ')}
          </div>
        )}

        {/* 拖拽上传 */}
        <div
          className={`dropzone ${importing ? '' : ''}`}
          onDragOver={(e) => e.preventDefault()}
          onDragEnter={(e) => e.currentTarget.classList.add('drag')}
          onDragLeave={(e) => e.currentTarget.classList.remove('drag')}
          onDrop={(e) => { e.currentTarget.classList.remove('drag'); onDrop(e); }}
          onClick={() => fileRef.current?.click()}
          style={{ marginTop: 12 }}
        >
          点击或拖拽 .txt / .md 文件到这里导入
          <input ref={fileRef} type="file" multiple accept=".txt,.md,text/plain,text/markdown"
                 onChange={onFileInput} style={{ display: 'none' }} />
        </div>
        <input ref={(el) => fileRef.current = el} type="file" hidden multiple
               onChange={onFileInput} />
        <div className="file-list">
          {files.map(({ file, id }) => (
            <div key={id} className="file-item">
              <span>📄 {file.name}</span>
              <small>{(file.size / 1024).toFixed(1)} KB</small>
              <button onClick={() => setFiles((fs) => fs.filter((f) => f.id !== id))}>×</button>
            </div>
          ))}
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" disabled={importing || !embedder || !files.length} onClick={runImport}>
            {importing ? '处理中…' : `导入 ${files.length} 个文件 → seekdb`}
          </button>
          <button onClick={() => { setFiles([]); setChunks([]); }}>清空</button>
          <div className="spacer" />
          <span className="small muted">chunk 预览: {chunks.length} 条</span>
        </div>

        {/* 导入进度 */}
        {importProgress.phase && (
          <div style={{ marginTop: 10 }}>
            <div className="small muted">
              {importProgress.phase} ({importProgress.done}/{importProgress.total})
              {importProgress.detail ? ` · ${importProgress.detail}` : ''}
            </div>
            {importProgress.total > 0 && (
              <div className="progress">
                <div className="progress-bar"
                     style={{ width: `${(importProgress.done / importProgress.total) * 100}%` }} />
              </div>
            )}
          </div>
        )}
      </section>

      {/* ============ 右侧: 检索 ============ */}
      <section className="panel">
        <h2>🔍 检索 <small>HybridSearch (全文 + 向量 + RRF)</small></h2>
        <textarea
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          placeholder="输入你的问题... (同时做全文关键词 + 语义向量检索, RRF 融合)"
          rows={2}
        />
        <div className="row" style={{ marginTop: 8 }}>
          <button className="primary" onClick={runSearch} disabled={searching || !embedder}>
            {searching ? '检索中…' : '🔍 搜索'}
          </button>
          <div className="spacer" />
          <span className="small muted">
            {metrics.e2eMs != null ? `端到端 ${metrics.e2eMs} ms` : ''}
          </span>
        </div>

        {/* Tabs: 对比三种检索模式 */}
        <div className="tabs" style={{ marginTop: 16 }}>
          {['hybrid', 'vector', 'text'].map((key) => (
            <button
              key={key}
              className={activeTab === key ? 'active' : ''}
              onClick={() => setActiveTab(key)}
            >
              {tabData[key].label}
              {tabData[key].data?.searchMs != null && (
                <span className="small muted" style={{ marginLeft: 6 }}>
                  {tabData[key].data.searchMs}ms
                </span>
              )}
            </button>
          ))}
        </div>

        {/* 结果 */}
        <div style={{ minHeight: 200 }}>
          {!results[activeTab] && (
            <div className="muted small">输入查询并点击搜索以查看结果。</div>
          )}
          {results[activeTab]?.error && (
            <div className="small" style={{ color: '#f53f3f' }}>{results[activeTab].error}</div>
          )}
          {resultRows.map((r, idx) => (
            <ResultItem key={r.id + idx} rank={idx + 1} item={r} />
          ))}
          {resultRows.length === 0 && results[activeTab] && !results[activeTab]?.error && (
            <div className="muted small">无结果。</div>
          )}
        </div>
      </section>

      {/* ============ 性能面板 ============ */}
      <section className="panel wide">
        <h2>⚡ 性能计时 <small>分阶段实测</small></h2>
        <div className="metric-grid">
          <Metric label="模型加载" value={metrics.modelLoadMs} unit="ms" />
          <Metric label="批量 Embedding" value={metrics.embedMs} unit="ms" />
          <Metric label="向量化吞吐" value={metrics.embedThroughput} unit="docs/s" />
          <Metric label="写入 seekdb" value={metrics.writeMs} unit="ms" />
          <Metric label="查询向量生成" value={metrics.queryEmbedMs} unit="ms" />
          <Metric label="seekdb 检索" value={metrics.searchMs} unit="ms" />
          <Metric label="端到端延迟" value={metrics.e2eMs} unit="ms" highlight />
        </div>
        <div className="small muted" style={{ marginTop: 10 }}>
          提示: 当前 device={effectiveDevice}, dtype={effectiveDtype}.
          {effectiveDevice === 'wasm' && backendInfo.webgpu && (
            <span style={{ color: '#ff7d00' }}> WebGPU 可用但未启用 — 请把顶部 device 改为 webgpu。</span>
          )}
          {effectiveDevice === 'wasm' && !backendInfo.webgpu && (
            <span> 当前浏览器不支持 WebGPU, 已降级到 WASM。</span>
          )}
        </div>
      </section>
    </div>
  );
}

/* ============================================================
 * 子组件
 * ============================================================ */
function Metric({ label, value, unit, highlight }) {
  return (
    <div className="metric-card" style={highlight ? { borderColor: '#165dff', background: '#f0f5ff' } : {}}>
      <div className="label">{label}</div>
      <div className="value">
        {value != null ? value : '—'}
        {value != null && <span className="unit">{unit}</span>}
      </div>
    </div>
  );
}

function ResultItem({ rank, item }) {
  const score = typeof item.score === 'number' ? item.score : null;
  return (
    <div className="result-item">
      <div className="meta">
        <span>#{rank}</span>
        <span>📄 {item.metadata?.source || 'unknown'}</span>
        <span className="score">{score != null ? score.toFixed(4) : ''}</span>
      </div>
      <div className="snippet">{item.document}</div>
    </div>
  );
}
