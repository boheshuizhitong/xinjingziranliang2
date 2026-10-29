/**
 * 前端 → seekdb 后端 API
 */

const BASE = '/api';

async function request(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json();
  if (!res.ok || json.error) {
    throw new Error(json.error || `HTTP ${res.status}`);
  }
  return json;
}

export const api = {
  health: () => request('GET', '/health'),
  listCollections: () => request('GET', '/collections'),
  createCollection: (name, dimension) => request('POST', '/collections', { name, dimension }),
  deleteCollection: (name) => request('DELETE', `/collections/${name}`),
  documents: (collection, batch) => request('POST', '/documents', { collection, batch }),
  search: (opts) => request('POST', '/search', opts),
  searchVector: (collection, queryVector, nResults = 10) =>
    request('POST', '/search/vector', { collection, queryVector, nResults }),
  searchText: (collection, queryText, nResults = 10) =>
    request('POST', '/search/text', { collection, queryText, nResults }),
};
