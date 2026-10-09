/**
 * Federated Retrieval Lab Module
 * Interactive multi-tier query sandbox (Vector + BM25 + Episodic + AST).
 */

import { api } from './api.js';
import { getState, setState } from './state.js';
import { showToast, escapeHtml } from './ui.js';

export async function populateRetrievalCollections() {
  try {
    const res = await api.getCollections();
    if (res.status === 'ok' && res.collections) {
      setState((prev) => ({
        retrieval: { ...prev.retrieval, collections: res.collections },
      }));
      const select = document.getElementById('select-retrieval-collection');
      if (select) {
        select.innerHTML = res.collections
          .map((c) => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${c.points_count || 0} pts)</option>`)
          .join('');
      }
    }
  } catch (err) {
    console.error('Failed to populate retrieval collections:', err);
  }
}

export async function executeRetrieval() {
  const promptInput = document.getElementById('retrieval-prompt-input');
  const prompt = promptInput ? promptInput.value.trim() : '';
  const colSelect = document.getElementById('select-retrieval-collection');
  const collection = colSelect ? colSelect.value : null;
  const { activeProject } = getState();

  if (!prompt) {
    showToast('Please enter a query prompt', 'warning');
    return;
  }

  setState((prev) => ({
    retrieval: { ...prev.retrieval, isSearching: true },
  }));

  const resultsContainer = document.getElementById('retrieval-results-container');
  if (resultsContainer) {
    resultsContainer.innerHTML = `
      <div class="p-8 text-center text-xs font-mono text-slate-300 animate-pulse">
        ⚡ Executing federated multi-tier query across Qdrant vectors and FalkorDB graph...
      </div>
    `;
  }

  try {
    const res = await api.executeRetrieval({
      prompt,
      collection,
      project: activeProject === 'all' ? null : activeProject,
      mode: 'hybrid',
    });

    setState((prev) => ({
      retrieval: { ...prev.retrieval, isSearching: false, lastResults: res },
    }));

    if (res.status === 'ok') {
      renderRetrievalResults(res.results || []);
    } else {
      if (resultsContainer) {
        resultsContainer.innerHTML = `<div class="p-4 text-xs font-mono text-rose-400 bg-rose-950/40 rounded-xl border border-rose-800">Error: ${escapeHtml(res.message)}</div>`;
      }
    }
  } catch (err) {
    setState((prev) => ({
      retrieval: { ...prev.retrieval, isSearching: false },
    }));
    if (resultsContainer) {
      resultsContainer.innerHTML = `<div class="p-4 text-xs font-mono text-rose-400 bg-rose-950/40 rounded-xl border border-rose-800">Error: ${escapeHtml(err.message)}</div>`;
    }
  }
}

function renderRetrievalResults(results) {
  const container = document.getElementById('retrieval-results-container');
  if (!container) return;

  if (results.length === 0) {
    container.innerHTML = `
      <div class="p-8 text-center border-2 border-dashed border-slate-800 rounded-xl text-xs text-slate-400 font-mono">
        No passages retrieved for this query.
      </div>
    `;
    return;
  }

  container.innerHTML = results
    .map((r, i) => {
      const score = typeof r.score === 'number' ? (r.score * 100).toFixed(1) : '—';
      const source = escapeHtml(r.file_path || r.source || 'Knowledge Base');
      const text = escapeHtml(r.text || r.content || '');

      return `
      <div class="p-4 rounded-xl bg-slate-900/90 border border-slate-700/80 shadow-md">
        <div class="flex items-center justify-between gap-2 mb-2 text-xs font-mono">
          <span class="text-indigo-300 font-semibold truncate max-w-md">${source}</span>
          <span class="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-600 font-bold">Match: ${score}%</span>
        </div>
        <pre class="p-3 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto whitespace-pre-wrap">${text}</pre>
      </div>
    `;
    })
    .join('');
}
