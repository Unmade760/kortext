/**
 * API Client Module
 * Unified, typed fetch client with error handling, timeouts, and JSON envelopes.
 */

const DEFAULT_TIMEOUT_MS = 15000;

export async function fetchJson(url, options = {}) {
  const { timeout = DEFAULT_TIMEOUT_MS, ...fetchOpts } = options;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);

  try {
    const res = await fetch(url, {
      ...fetchOpts,
      signal: controller.signal,
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        ...(fetchOpts.headers || {}),
      },
    });
    clearTimeout(id);

    if (!res.ok) {
      let errDetail = `${res.status} ${res.statusText}`;
      try {
        const errJson = await res.json();
        if (errJson.message) errDetail = errJson.message;
      } catch (_) {}
      throw new Error(errDetail);
    }

    return await res.json();
  } catch (err) {
    clearTimeout(id);
    if (err.name === 'AbortError') {
      throw new Error(`Request timed out after ${timeout}ms: ${url}`);
    }
    throw err;
  }
}

export const api = {
  // Telemetry & Health
  getStatus: () => fetchJson('/api/status'),
  getTelemetry: () => fetchJson('/api/telemetry'),
  getWatcherStatus: () => fetchJson('/api/watcher/status'),
  getCacheStats: () => fetchJson('/api/cache/stats'),
  clearCache: () => fetchJson('/api/cache/clear', { method: 'POST' }),

  // Graphs
  getGraphs: () => fetchJson('/api/graphs'),
  getGraph: (graphType = 'episodic', clean = true, graphName = null) => {
    const params = new URLSearchParams({ graph_type: graphType, clean: String(clean) });
    if (graphName) params.append('graph_name', graphName);
    return fetchJson(`/api/graph?${params.toString()}`);
  },

  // Symbols & Blast Radius
  getSymbols: (query = null, graphName = null) => {
    const params = new URLSearchParams();
    if (query) params.append('q', query);
    if (graphName) params.append('graph_name', graphName);
    return fetchJson(`/api/symbols?${params.toString()}`);
  },
  getSymbolImpact: ({ target, direction = 'upstream', maxDepth = 3, graphName = null }) => {
    const params = new URLSearchParams({
      target,
      direction,
      max_depth: String(maxDepth),
    });
    if (graphName) params.append('graph_name', graphName);
    return fetchJson(`/api/symbols/impact?${params.toString()}`);
  },

  // Task DAG
  getTasks: (projectId = null) => {
    const params = new URLSearchParams({ include_graph: 'true' });
    if (projectId) params.append('project_id', projectId);
    return fetchJson(`/api/tasks?${params.toString()}`);
  },
  manageTask: (payload) =>
    fetchJson('/api/tasks', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Journal
  getJournal: (category = null) => {
    const params = new URLSearchParams();
    if (category && category !== 'all') params.append('category', category);
    return fetchJson(`/api/journal?${params.toString()}`);
  },
  getJournalEntry: (entryPath) =>
    fetchJson(`/api/journal/entry?path=${encodeURIComponent(entryPath)}`),

  // Retrieval & Collections
  getCollections: () => fetchJson('/api/collections'),
  createCollection: (name) =>
    fetchJson('/api/collections', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  executeRetrieval: ({ prompt, collection = null, project = null, mode = 'hybrid' }) =>
    fetchJson('/api/retrieval/query', {
      method: 'POST',
      body: JSON.stringify({ prompt, collection, project, mode }),
    }),

  // Dream Mode
  triggerDream: ({ project = 'kortext', purgeStale = false, consolidations = null, distilledSkills = null } = {}) =>
    fetchJson('/api/dream', {
      method: 'POST',
      body: JSON.stringify({
        project,
        purge_stale: purgeStale,
        consolidations,
        distilled_skills: distilledSkills,
      }),
    }),

  // SCIP Ingestion
  runScipAuto: () => fetchJson('/api/scip/auto', { method: 'POST' }),
};
