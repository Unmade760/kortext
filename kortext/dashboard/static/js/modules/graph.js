/**
 * Anti-Hairball Knowledge Graph Module
 * Vis.js interactive graph explorer with macro-clustering, Louvain subsystems,
 * degree filtering, neighborhood isolation, and relationship palettes.
 */

import { api } from './api.js';
import { getState, setState } from './state.js';
import { showToast, escapeHtml } from './ui.js';

let network = null;
let allNodes = [];
let allEdges = [];
let nodesDataSet = null;
let edgesDataSet = null;

export async function populateGraphSelector() {
  try {
    const res = await api.getGraphs();
    if (res.status === 'ok' && res.graphs) {
      const select = document.getElementById('select-graph-type');
      if (select) {
        const current = getState().graph.currentName || 'kortext';
        select.innerHTML = res.graphs
          .map((g) => `<option value="${escapeHtml(g)}" ${g === current ? 'selected' : ''}>${escapeHtml(g)}</option>`)
          .join('');
      }
    }
  } catch (err) {
    console.error('Failed to populate graphs:', err);
  }
}

export async function loadGraph() {
  const select = document.getElementById('select-graph-type');
  const graphName = select ? select.value : 'kortext';
  const isSymbols = graphName.includes('symbol') || graphName.includes('doc');
  const graphType = isSymbols ? 'symbols' : 'episodic';
  const { clean } = getState().graph;

  setState((prev) => ({
    graph: { ...prev.graph, type: graphType, currentName: graphName },
  }));

  try {
    const data = await api.getGraph(graphType, clean, graphName);
    if (data.status === 'ok') {
      allNodes = data.nodes || [];
      allEdges = data.edges || [];
      initRelationshipPalette(allEdges);
      applyGraphFilters();
    } else {
      showToast(`Failed to load graph: ${data.message}`, 'error');
    }
  } catch (err) {
    showToast(`Error fetching graph: ${err.message}`, 'error');
  }
}

export function initRelationshipPalette(edges) {
  const relations = new Set(edges.map((e) => e.label || 'LINKS_TO'));
  setState((prev) => ({
    graph: {
      ...prev.graph,
      allRelations: relations,
      activeRelations: new Set(relations),
    },
  }));

  const container = document.getElementById('rel-palette-chips');
  if (!container) return;

  container.innerHTML = Array.from(relations)
    .map(
      (rel) => `
    <button 
      class="rel-chip px-2 py-0.5 rounded text-[11px] font-mono border transition flex items-center gap-1 bg-indigo-950/80 text-indigo-300 border-indigo-700/60"
      data-rel="${escapeHtml(rel)}"
      onclick="window.kortextGraph.toggleRelFilter('${escapeHtml(rel)}')"
    >
      <span class="w-1.5 h-1.5 rounded-full bg-indigo-400"></span> ${escapeHtml(rel)}
    </button>
  `
    )
    .join('');
}

export function toggleRelFilter(rel) {
  const { graph } = getState();
  const nextRels = new Set(graph.activeRelations);
  if (nextRels.has(rel)) {
    nextRels.delete(rel);
  } else {
    nextRels.add(rel);
  }
  setState((prev) => ({ graph: { ...prev.graph, activeRelations: nextRels } }));

  // Update button visual
  const btn = document.querySelector(`.rel-chip[data-rel="${rel}"]`);
  if (btn) {
    if (nextRels.has(rel)) {
      btn.className = 'rel-chip px-2 py-0.5 rounded text-[11px] font-mono border transition flex items-center gap-1 bg-indigo-950/80 text-indigo-300 border-indigo-700/60';
    } else {
      btn.className = 'rel-chip px-2 py-0.5 rounded text-[11px] font-mono border transition flex items-center gap-1 bg-slate-900 text-slate-500 border-slate-800 opacity-60';
    }
  }

  applyGraphFilters();
}

export function handleMinDegreeChange(minDeg) {
  const deg = parseInt(minDeg, 10) || 0;
  const label = document.getElementById('label-min-degree');
  if (label) label.textContent = String(deg);
  setState((prev) => ({ graph: { ...prev.graph, minDegree: deg } }));
  applyGraphFilters();
}

export function applyGraphFilters() {
  const { minDegree, activeRelations, isolatedNeighborhood, selectedNodeId } = getState().graph;

  let filteredNodes = allNodes.filter((n) => (n.degree || 0) >= minDegree);
  const allowedNodeIds = new Set(filteredNodes.map((n) => n.id));

  let filteredEdges = allEdges.filter(
    (e) =>
      allowedNodeIds.has(e.from) &&
      allowedNodeIds.has(e.to) &&
      (!e.label || activeRelations.has(e.label))
  );

  // If neighborhood isolation is active
  if (isolatedNeighborhood && selectedNodeId) {
    const neighborIds = new Set([selectedNodeId]);
    filteredEdges.forEach((e) => {
      if (e.from === selectedNodeId) neighborIds.add(e.to);
      if (e.to === selectedNodeId) neighborIds.add(e.from);
    });
    filteredNodes = filteredNodes.filter((n) => neighborIds.has(n.id));
    filteredEdges = filteredEdges.filter((e) => neighborIds.has(e.from) && neighborIds.has(e.to));
  }

  renderGraph(filteredNodes, filteredEdges);
}

export function renderGraph(nodes, edges) {
  const container = document.getElementById('network-graph');
  if (!container || !window.vis) return;

  // Format high-contrast Vis.js nodes
  const visNodes = nodes.map((n) => {
    const isDoc = n.group === 'document';
    const isTask = n.group === 'task';
    const isProj = n.group === 'project';
    const isDecision = n.group === 'decision';
    const isSubsys = n.group === 'subsystem';

    const bg = isTask
      ? '#10b981'
      : isProj
      ? '#3b82f6'
      : isDecision
      ? '#8b5cf6'
      : isSubsys
      ? '#f59e0b'
      : isDoc
      ? '#06b6d4'
      : '#6366f1';

    return {
      ...n,
      color: {
        background: bg,
        border: '#ffffff',
        highlight: { background: '#ffffff', border: bg },
      },
      font: {
        color: '#f8fafc',
        size: 11,
        face: 'monospace',
        strokeWidth: 2,
        strokeColor: '#090d16',
      },
      shape: isDoc ? 'box' : isTask || isProj ? 'box' : 'dot',
      size: Math.min(30, Math.max(12, (n.degree || 1) * 3)),
    };
  });

  const visEdges = edges.map((e) => ({
    ...e,
    color: { color: 'rgba(148, 163, 184, 0.4)', highlight: '#818cf8' },
    arrows: 'to',
    font: { color: '#cbd5e1', size: 9, align: 'middle', strokeWidth: 2, strokeColor: '#090d16' },
  }));

  nodesDataSet = new window.vis.DataSet(visNodes);
  edgesDataSet = new window.vis.DataSet(visEdges);

  const options = {
    nodes: { borderWidth: 1.5 },
    edges: { smooth: { type: 'continuous', roundness: 0.2 } },
    physics: {
      barnesHut: { gravitationalConstant: -3000, springLength: 95, springConstant: 0.04 },
      stabilization: { iterations: 120 },
    },
    interaction: { hover: true, tooltipDelay: 100, zoomView: true },
  };

  if (network) network.destroy();
  network = new window.vis.Network(container, { nodes: nodesDataSet, edges: edgesDataSet }, options);

  network.on('click', (params) => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      const node = allNodes.find((n) => n.id === nodeId);
      if (node) openDrawer(node);
    } else {
      closeDrawer();
    }
  });
}

// Anti-Hairball Macro-Module Clustering
export function toggleMacroClustering() {
  if (!network) return;
  const { clusterMode } = getState().graph;
  if (clusterMode === 'module') {
    unclusterAll();
    setState((prev) => ({ graph: { ...prev.graph, clusterMode: 'none' } }));
    showToast('Macro clusters expanded', 'info', 1500);
  } else {
    clusterByProperty('cluster_id');
    setState((prev) => ({ graph: { ...prev.graph, clusterMode: 'module' } }));
    showToast('Clustered by module packages', 'success', 2000);
  }
}

function clusterByProperty(propName) {
  const clusters = {};
  allNodes.forEach((n) => {
    const val = n[propName] || 'other';
    if (!clusters[val]) clusters[val] = [];
    clusters[val].push(n.id);
  });

  Object.entries(clusters).forEach(([cName, ids]) => {
    if (ids.length <= 1) return;
    network.cluster({
      joinCondition: (nodeOptions) => ids.includes(nodeOptions.id),
      clusterNodeProperties: {
        id: `cluster:${cName}`,
        label: `${cName} (${ids.length})`,
        color: { background: '#312e81', border: '#818cf8' },
        font: { color: '#ffffff', size: 12, bold: true },
        shape: 'database',
        size: 35,
      },
    });
  });

  network.on('doubleClick', (params) => {
    if (params.nodes.length === 1 && String(params.nodes[0]).startsWith('cluster:')) {
      network.openCluster(params.nodes[0]);
    }
  });
}

function unclusterAll() {
  if (!network) return;
  const nodeIds = nodesDataSet.getIds();
  nodeIds.forEach((id) => {
    if (network.isCluster(id)) {
      network.openCluster(id);
    }
  });
}

// Neighborhood Isolation
export function toggleNeighborhoodIsolation() {
  const { selectedNodeId, isolatedNeighborhood } = getState().graph;
  if (!selectedNodeId) {
    showToast('Select a node first to isolate its neighborhood', 'warning');
    return;
  }
  const nextIso = !isolatedNeighborhood;
  setState((prev) => ({ graph: { ...prev.graph, isolatedNeighborhood: nextIso } }));
  applyGraphFilters();
  showToast(nextIso ? `Isolated neighborhood for ${selectedNodeId}` : 'Exited neighborhood isolation', 'info');
}

// Physics Freeze Toggle
export function toggleGraphFreeze() {
  if (!network) return;
  const nextFrozen = !getState().graph.isFrozen;
  setState((prev) => ({ graph: { ...prev.graph, isFrozen: nextFrozen } }));
  network.setOptions({ physics: { enabled: !nextFrozen } });
  const btn = document.getElementById('btn-freeze-graph');
  if (btn) {
    btn.innerHTML = nextFrozen
      ? '<span class="text-amber-400 font-bold">❄ Frozen</span>'
      : '<span>Freeze Physics</span>';
  }
  showToast(nextFrozen ? 'Physics frozen' : 'Physics enabled', 'info', 1500);
}

// Node Details Drawer
export function openDrawer(node) {
  setState((prev) => ({ graph: { ...prev.graph, selectedNodeId: node.id } }));
  const drawer = document.getElementById('node-drawer');
  if (!drawer) return;

  const content = document.getElementById('drawer-content');
  if (content) {
    content.innerHTML = `
      <div class="space-y-3 font-mono text-xs">
        <div>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-700/60 uppercase">${escapeHtml(
            node.group || 'Node'
          )}</span>
          <h3 class="text-sm font-bold text-slate-100 mt-1 break-words">${escapeHtml(node.label || node.id)}</h3>
        </div>
        <div class="p-2.5 rounded bg-slate-950 border border-slate-800 space-y-1 text-slate-300">
          <div><span class="text-slate-400">ID:</span> <span class="text-slate-200 select-all">${escapeHtml(node.id)}</span></div>
          <div><span class="text-slate-400">Degree:</span> <span class="text-emerald-400 font-bold">${node.degree || 0}</span></div>
          ${node.cluster_name ? `<div><span class="text-slate-400">Cluster:</span> ${escapeHtml(node.cluster_name)}</div>` : ''}
        </div>
        <div class="flex gap-2 pt-2">
          <button 
            onclick="window.kortextGraph.toggleNeighborhoodIsolation()"
            class="flex-1 py-1.5 px-3 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition"
          >
            Isolate Ego Network
          </button>
        </div>
      </div>
    `;
  }
  drawer.classList.remove('hidden');
}

export function closeDrawer() {
  const drawer = document.getElementById('node-drawer');
  if (drawer) drawer.classList.add('hidden');
}

export function zoomGraph(delta) {
  if (!network) return;
  const scale = network.getScale() + delta;
  network.moveTo({ scale: Math.max(0.1, Math.min(3, scale)) });
}

export function fitGraph() {
  if (network) network.fit({ animation: { duration: 400 } });
}
