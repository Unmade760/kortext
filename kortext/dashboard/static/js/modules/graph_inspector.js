/**
 * Kortext Dashboard - Graph Companion Inspector & Relationship Palette
 * Side panel inspecting nodes, incoming/outgoing edges, and relationship filtering.
 */

import { state } from './state.js';
import { getEdgeStyle, applyGraphFilters, flyToNode, isolateNeighborhood } from './graph.js';
import { escapeHtml } from './ui.js';

export function initRelationshipPalette(edges) {
  const container = document.getElementById('rel-filter-list');
  if (!container) return;
  state.graph.relCounts = {};
  edges.forEach(e => {
    const lbl = (e.label || 'UNKNOWN').toUpperCase().trim();
    state.graph.relCounts[lbl] = (state.graph.relCounts[lbl] || 0) + 1;
  });

  const uniqueRels = Object.keys(state.graph.relCounts).sort();
  state.graph.activeRelFilters = new Set(uniqueRels);

  if (uniqueRels.length === 0) {
    container.innerHTML = '<div class="text-slate-400 py-3 text-center text-xs">No relationships in view</div>';
    return;
  }

  container.innerHTML = uniqueRels.map(rel => {
    const style = getEdgeStyle(rel, false);
    const count = state.graph.relCounts[rel] || 0;
    return `
      <label class="flex items-center justify-between p-1.5 rounded hover:bg-slate-800/60 cursor-pointer select-none transition group">
        <div class="flex items-center gap-2">
          <input type="checkbox" id="filter-rel-${rel}" checked onchange="toggleRelFilter('${rel}', this.checked)" class="rounded border-slate-700 text-indigo-500 w-3 h-3">
          <span class="w-3 h-0.5" style="background-color: ${style.color};"></span>
          <span class="text-slate-300 group-hover:text-white font-mono text-[10px]">${rel}</span>
        </div>
        <span class="text-[9px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-semibold">${count}</span>
      </label>
    `;
  }).join('');
}

export function toggleRelFilter(rel, isChecked) {
  if (isChecked) state.graph.activeRelFilters.add(rel);
  else state.graph.activeRelFilters.delete(rel);
  applyGraphFilters();
}

export function setAllRelFilters(enable) {
  const container = document.getElementById('rel-filter-list');
  if (!container) return;
  container.querySelectorAll('input[type="checkbox"]').forEach(input => {
    input.checked = enable;
    const rel = input.id.replace('filter-rel-', '');
    if (enable) state.graph.activeRelFilters.add(rel);
    else state.graph.activeRelFilters.delete(rel);
  });
  applyGraphFilters();
}

export function applyRelPreset(preset) {
  const container = document.getElementById('rel-filter-list');
  if (!container) return;
  container.querySelectorAll('input[type="checkbox"]').forEach(input => {
    const rel = input.id.replace('filter-rel-', '').toUpperCase();
    let shouldCheck = preset === 'all'
      || (preset === 'calls' && (rel.includes('REFERENCES') || rel.includes('CALLS')))
      || (preset === 'structure' && (rel.includes('DEFINED_IN') || rel.includes('IMPORTS') || rel.includes('LINKS') || rel.includes('BELONGS_TO')))
      || (preset === 'types' && (rel.includes('IMPLEMENTS') || rel.includes('TYPE')));
    input.checked = shouldCheck;
    if (shouldCheck) state.graph.activeRelFilters.add(rel);
    else state.graph.activeRelFilters.delete(rel);
  });
  applyGraphFilters();
}

export function openDrawer(node) {
  const content = document.getElementById('inspector-content');
  const badge = document.getElementById('inspector-badge');
  if (!content || !node) return;

  if (badge) {
    badge.textContent = (node.group || 'Node').toUpperCase();
    badge.className = 'text-[9px] font-mono px-2 py-0.5 rounded uppercase font-semibold border bg-indigo-950/80 text-indigo-300 border-indigo-500/50';
    badge.classList.remove('hidden');
  }

  const connectedEdges = state.graph.edgesDataSet ? state.graph.edgesDataSet.get({
    filter: e => e.from === node.id || e.to === node.id
  }) : [];
  const outgoing = connectedEdges.filter(e => e.from === node.id);
  const incoming = connectedEdges.filter(e => e.to === node.id);

  const renderRel = (e, isOut) => {
    const otherId = isOut ? e.to : e.from;
    const displayName = otherId.split('/').slice(-2).join('/');
    return `
      <div class="flex items-center justify-between p-1.5 rounded bg-slate-950/70 border border-slate-800 text-[11px] font-mono">
        <span class="text-indigo-400 font-bold shrink-0">${isOut ? '→' : '←'} ${e.label}</span>
        <span class="text-slate-300 truncate max-w-[120px]" title="${otherId}">${displayName}</span>
        <button onclick="flyToNode('${otherId}')" class="px-1.5 py-0.5 bg-slate-800 hover:bg-slate-700 text-indigo-300 rounded text-[10px]">Focus</button>
      </div>
    `;
  };

  content.innerHTML = `
    <div class="space-y-2.5">
      <div class="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1 font-mono text-xs">
        <div class="font-bold text-white truncate" title="${node.full_name || node.id}">${node.label || node.id}</div>
        <div class="text-[10px] text-slate-400 truncate">ID: ${node.id}</div>
        <div class="flex justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-800">
          <span>Subsystem:</span> <span class="text-indigo-400 font-semibold">${node.cluster_name || 'Core'}</span>
        </div>
        <button onclick="isolateNeighborhood('${node.id}')" class="w-full mt-2 py-1.5 rounded bg-indigo-600/30 hover:bg-indigo-600/60 border border-indigo-500/50 text-indigo-300 text-xs font-semibold">
          Isolate Neighborhood
        </button>
      </div>
      <div class="space-y-1">
        <div class="text-xs font-semibold text-slate-400">Outgoing (${outgoing.length}):</div>
        <div class="space-y-1 max-h-32 overflow-y-auto">${outgoing.length ? outgoing.map(e => renderRel(e, true)).join('') : '<span class="text-slate-400 text-[10px]">None</span>'}</div>
      </div>
      <div class="space-y-1 pt-1 border-t border-slate-800">
        <div class="text-xs font-semibold text-slate-400">Incoming (${incoming.length}):</div>
        <div class="space-y-1 max-h-32 overflow-y-auto">${incoming.length ? incoming.map(e => renderRel(e, false)).join('') : '<span class="text-slate-400 text-[10px]">None</span>'}</div>
      </div>
    </div>
  `;
}

export function closeDrawer() {
  const content = document.getElementById('inspector-content');
  const badge = document.getElementById('inspector-badge');
  if (badge) badge.classList.add('hidden');
  if (content) content.innerHTML = '<div class="text-slate-400 text-xs py-4 text-center font-mono">Click any node to inspect relationships.</div>';
}

export function openClusterDrawer(clusterId) {
  const content = document.getElementById('inspector-content');
  const badge = document.getElementById('inspector-badge');
  if (badge) {
    badge.textContent = 'Macro Subsystem';
    badge.className = 'text-[9px] font-mono px-2 py-0.5 rounded uppercase font-semibold border bg-indigo-950/80 text-indigo-300 border-indigo-500/50';
    badge.classList.remove('hidden');
  }
  const cleanId = clusterId.replace('cluster:', '');
  const count = state.graph.network ? state.graph.network.getNodesInCluster(clusterId).length : 0;
  if (content) {
    content.innerHTML = `
      <div class="space-y-2.5 font-mono text-xs">
        <div class="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
          <div class="font-bold text-white">📦 Subsystem: ${cleanId}</div>
          <div class="text-[10px] text-slate-400">Contains ${count} components.</div>
        </div>
        <button onclick="state.graph.network.openCluster('${clusterId}')" class="w-full py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-semibold">
          Expand This Subsystem
        </button>
      </div>
    `;
  }
}
