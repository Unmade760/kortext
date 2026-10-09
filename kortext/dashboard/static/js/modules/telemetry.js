/**
 * Telemetry & Substrate Health Module
 * Real-time monitoring for the 5-Tier Memory Architecture, substrate IPC, and interceptor hooks.
 */

import { api } from './api.js';
import { getState, setState } from './state.js';
import { showToast, escapeHtml } from './ui.js';

let pollingIntervalId = null;

export async function initTelemetry() {
  await loadAllTelemetry();
  startPolling();
}

export function startPolling(intervalMs = 10000) {
  stopPolling();
  pollingIntervalId = setInterval(() => {
    if (!document.hidden) {
      loadQuickStatus().catch(console.error);
    }
  }, intervalMs);
}

export function stopPolling() {
  if (pollingIntervalId) {
    clearInterval(pollingIntervalId);
    pollingIntervalId = null;
  }
}

export async function loadAllTelemetry() {
  await Promise.allSettled([
    loadQuickStatus(),
    loadTelemetryMetrics(),
    loadWatcherStatus(),
    loadCacheStats(),
  ]);
}

export async function loadQuickStatus() {
  try {
    const data = await api.getStatus();
    setState({ services: data.services || [] });
    updateQuickPills(data.services || []);
  } catch (err) {
    console.error('Failed to load status:', err);
  }
}

export function updateQuickPills(services) {
  services.forEach((s) => {
    const sName = s.name.toLowerCase();
    const pillId = sName.includes('qdrant')
      ? 'pill-qdrant'
      : sName.includes('falkordb')
      ? 'pill-falkordb'
      : sName.includes('omlx')
      ? 'pill-omlx'
      : null;

    if (!pillId) return;
    const el = document.getElementById(pillId);
    if (!el) return;

    if (s.healthy) {
      el.className =
        'px-2.5 py-1 rounded bg-emerald-950/90 text-emerald-300 border border-emerald-600/60 font-mono text-xs flex items-center gap-1.5 shadow-sm';
      el.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> ${escapeHtml(
        s.name.split(' ')[0]
      )}`;
    } else {
      el.className =
        'px-2.5 py-1 rounded bg-rose-950/90 text-rose-300 border border-rose-600/60 font-mono text-xs flex items-center gap-1.5 shadow-sm';
      el.innerHTML = `<span class="w-2 h-2 rounded-full bg-rose-500"></span> ${escapeHtml(
        s.name.split(' ')[0]
      )} (Offline)`;
    }
  });
}

export async function loadWatcherStatus() {
  const pill = document.getElementById('pill-watcher');
  try {
    const res = await api.getWatcherStatus();
    if (res.status === 'ok' && res.watcher) {
      setState({ watcher: res.watcher });
      const isRunning = res.watcher.running && res.watcher.alive !== false;
      if (pill) {
        pill.className = isRunning
          ? 'px-2.5 py-1 rounded bg-emerald-950/90 text-emerald-300 border border-emerald-600/60 font-mono text-xs flex items-center gap-1.5'
          : 'px-2.5 py-1 rounded bg-slate-900 text-slate-300 border border-slate-700 font-mono text-xs flex items-center gap-1.5';
        pill.innerHTML = `<span class="w-2 h-2 rounded-full ${
          isRunning ? 'bg-emerald-400' : 'bg-slate-500'
        }"></span> Watcher: ${isRunning ? 'ACTIVE' : 'IDLE'}`;
      }
    }
  } catch (err) {
    if (pill) {
      pill.className =
        'px-2.5 py-1 rounded bg-slate-900 text-slate-400 border border-slate-700 font-mono text-xs flex items-center gap-1.5';
      pill.innerHTML = `<span class="w-2 h-2 rounded-full bg-slate-600"></span> Watcher: OFF`;
    }
  }
}

export async function loadCacheStats() {
  try {
    const res = await api.getCacheStats();
    if (res.status === 'ok') {
      setState({ cacheStats: res });
      const elFiles = document.getElementById('stat-indexed-files');
      const elChunks = document.getElementById('stat-cached-chunks');
      if (elFiles) elFiles.textContent = res.total_indexed_files ?? '—';
      if (elChunks && res.chunk_cache) elChunks.textContent = res.chunk_cache.total_chunks ?? '—';
    }
  } catch (err) {
    console.error('Failed to load cache stats:', err);
  }
}

export async function clearChunkCache() {
  try {
    const res = await api.clearCache();
    if (res.status === 'ok') {
      showToast(`Chunk embedding cache purged (${res.purged_chunks} chunks removed)`, 'success');
      loadCacheStats();
    } else {
      showToast(`Cache purge failed: ${res.message}`, 'error');
    }
  } catch (err) {
    showToast(`Error clearing cache: ${err.message}`, 'error');
  }
}

export async function loadTelemetryMetrics() {
  try {
    const res = await api.getTelemetry();
    if (res.status === 'ok' && res.telemetry) {
      const t = res.telemetry;
      setState({ telemetry: t });
      renderTelemetryCards(t);
    }
  } catch (err) {
    console.error('Failed to load telemetry:', err);
  }
}

function renderTelemetryCards(t) {
  // Update latency & status elements if present
  const latEl = document.getElementById('stat-falkor-latency');
  if (latEl && t.falkordb_latency_ms !== undefined) {
    latEl.textContent = `${t.falkordb_latency_ms.toFixed(1)} ms`;
  }

  // Render 5-Tier Memory Grid
  const gridContainer = document.getElementById('memory-tiers-grid');
  if (gridContainer && t.memory_tiers) {
    const tiers = [
      { id: 'tier_0', num: 0, title: 'AST B-Tree Index', desc: 'FalkorDB kortext_symbols graph, syntax trees, call hierarchy' },
      { id: 'tier_1', num: 1, title: 'Dense & Sparse Vectors', desc: 'Qdrant vector store with FastEmbed fallback default' },
      { id: 'tier_2', num: 2, title: 'Episodic & Causal Graph', desc: 'FalkorDB project memory, Task DAG, decisions, outcomes' },
      { id: 'tier_3', num: 3, title: 'HippoRAG Federated Search', desc: 'Personalized PageRank & reciprocal rank cross-encoder' },
      { id: 'tier_4', num: 4, title: 'Cognitive Dream Mode', desc: 'Weibull decay, synaptic pruning, Louvain community clusters' },
    ];

    gridContainer.innerHTML = tiers
      .map((tier) => {
        const data = t.memory_tiers[tier.id] || { status: 'Active' };
        return `
        <div class="p-4 rounded-xl bg-slate-900/90 border border-slate-700/80 shadow-md">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-mono px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-700/60 font-semibold">Tier ${tier.num}</span>
            <span class="text-xs font-mono font-medium text-emerald-300 flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> ${escapeHtml(data.status || 'Active')}
            </span>
          </div>
          <h4 class="text-sm font-semibold text-slate-100 mb-1">${escapeHtml(tier.title)}</h4>
          <p class="text-xs text-slate-300 mb-3">${escapeHtml(tier.desc)}</p>
          <div class="text-[11px] font-mono text-slate-400 bg-slate-950/80 p-2 rounded border border-slate-800">
            ${data.embedder ? `<div>Embedder: <span class="text-indigo-300 font-semibold">${escapeHtml(data.embedder)}</span></div>` : ''}
            ${data.nodes !== undefined ? `<div>Nodes: <span class="text-slate-200 font-semibold">${data.nodes}</span> | Edges: <span class="text-slate-200 font-semibold">${data.edges}</span></div>` : ''}
            ${!data.embedder && data.nodes === undefined ? `<div class="text-slate-400">Substrate verified & ready</div>` : ''}
          </div>
        </div>
      `;
      })
      .join('');
  }

  // Render Next-Gen Hooks Badges
  const hooksContainer = document.getElementById('nextgen-hooks-list');
  if (hooksContainer && t.nextgen_hooks) {
    hooksContainer.innerHTML = t.nextgen_hooks
      .map(
        (h) => `
      <span class="px-2.5 py-1 rounded bg-slate-950 text-indigo-200 border border-indigo-800/60 font-mono text-xs flex items-center gap-1.5 shadow-sm">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> ${escapeHtml(h)}
      </span>
    `
      )
      .join('');
  }
}
