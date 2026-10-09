/**
 * Kortext Dashboard - Knowledge Graph Explorer
 * Anti-hairball clustering, non-overlapping curved edges, ego-network isolation, and companion sidebar.
 */

import { state } from './state.js';
import * as api from './api.js';
import { toast, escapeHtml } from './ui.js';

export function getEdgeStyle(label, isMention = false) {
  const lbl = (label || '').toUpperCase().trim();

  if (lbl === 'DEFINED_IN') {
    return { color: '#06b6d4', highlight: '#22d3ee', hover: '#38bdf8', width: 1.8, dashes: false, fontColor: '#38bdf8', badgeBg: 'rgba(8, 20, 36, 0.94)' };
  }
  if (lbl === 'REFERENCES' || lbl.startsWith('REFERENCES') || lbl === 'CALLS' || lbl.startsWith('CALLS')) {
    return { color: '#10b981', highlight: '#34d399', hover: '#6ee7b7', width: 2.0, dashes: false, fontColor: '#34d399', badgeBg: 'rgba(6, 28, 20, 0.94)' };
  }
  if (lbl === 'IMPORTS' || lbl.includes('IMPORTS')) {
    return { color: '#8b5cf6', highlight: '#a78bfa', hover: '#c4b5fd', width: 1.8, dashes: false, fontColor: '#a78bfa', badgeBg: 'rgba(22, 14, 46, 0.94)' };
  }
  if (lbl === 'IMPLEMENTS') {
    return { color: '#ec4899', highlight: '#f472b6', hover: '#fbcfe8', width: 2.0, dashes: [6, 4], fontColor: '#f472b6', badgeBg: 'rgba(38, 10, 24, 0.94)' };
  }
  if (lbl === 'TYPE_OF' || lbl === 'TYPE' || lbl === 'TAG') {
    return { color: '#f97316', highlight: '#fb923c', hover: '#fed7aa', width: 1.8, dashes: [3, 4], fontColor: '#fb923c', badgeBg: 'rgba(36, 16, 6, 0.94)' };
  }
  if (lbl.includes('DEPENDS') || lbl === 'BLOCKS') {
    return { color: '#f43f5e', highlight: '#fb7185', hover: '#fda4af', width: 2.0, dashes: false, fontColor: '#fb7185', badgeBg: 'rgba(36, 8, 14, 0.94)' };
  }
  if (lbl === 'SUPERSEDES') {
    return { color: '#ef4444', highlight: '#f87171', hover: '#fca5a5', width: 2.2, dashes: [6, 3], fontColor: '#f87171', badgeBg: 'rgba(40, 8, 8, 0.94)' };
  }
  if (lbl === 'RELATES_TO' || lbl === 'HAS_TASK' || lbl === 'PRODUCED_OUTCOME') {
    return { color: '#0ea5e9', highlight: '#38bdf8', hover: '#7dd3fc', width: 1.8, dashes: false, fontColor: '#38bdf8', badgeBg: 'rgba(8, 24, 40, 0.94)' };
  }
  if (lbl === 'LINKS_TO') {
    return { color: '#14b8a6', highlight: '#2dd4bf', hover: '#5eead4', width: 1.8, dashes: false, fontColor: '#2dd4bf', badgeBg: 'rgba(6, 30, 28, 0.94)' };
  }
  if (isMention || lbl === 'MENTIONS') {
    return { color: '#475569', highlight: '#94a3b8', hover: '#cbd5e1', width: 1.2, dashes: [4, 4], fontColor: '#94a3b8', badgeBg: 'rgba(15, 23, 42, 0.94)' };
  }
  return { color: '#6366f1', highlight: '#818cf8', hover: '#c7d2fe', width: 1.6, dashes: false, fontColor: '#818cf8', badgeBg: 'rgba(15, 23, 42, 0.94)' };
}

export function formatEdgesNonOverlapping(edgesData) {
  const pairEdgesMap = new Map();
  edgesData.forEach(e => {
    const u = e.from < e.to ? e.from : e.to;
    const v = e.from < e.to ? e.to : e.from;
    const pairKey = `${u}|||${v}`;
    if (!pairEdgesMap.has(pairKey)) pairEdgesMap.set(pairKey, []);
    pairEdgesMap.get(pairKey).push(e);
  });

  const formatted = [];
  pairEdgesMap.forEach((edgeGroup) => {
    const total = edgeGroup.length;
    edgeGroup.forEach((e, idx) => {
      const style = getEdgeStyle(e.label, e.is_mention);
      let smooth = { enabled: true, type: 'curvedCW', roundness: 0.16 };
      if (total > 1) {
        const step = Math.floor(idx / 2);
        const isCW = (idx % 2 === 0);
        smooth = { enabled: true, type: isCW ? 'curvedCW' : 'curvedCCW', roundness: 0.18 + (step * 0.16) };
      }
      formatted.push({
        ...e,
        arrows: e.arrows || { to: { enabled: true, scaleFactor: 0.75 } },
        color: { color: style.color, highlight: style.highlight, hover: style.hover },
        originalColor: { color: style.color, highlight: style.highlight, hover: style.hover },
        width: style.width,
        originalWidth: style.width,
        smooth,
        dashes: style.dashes,
        font: { size: 9, align: 'middle', color: style.fontColor, face: 'ui-monospace, monospace', background: style.badgeBg },
      });
    });
  });
  return formatted;
}

export async function populateGraphSelector() {
  const select = document.getElementById('select-graph-type');
  if (!select) return;
  try {
    const data = await api.getGraphs();
    if (data.status === 'ok' && data.graphs && data.graphs.length > 0) {
      const currentVal = select.value || 'kortext';
      const validGraphs = data.graphs.filter(g => g !== 'default_db' && !g.endsWith('_test'));
      select.innerHTML = validGraphs.map(g => {
        let label = `Graph (${g})`;
        if (g === 'kortext') label = `🧠 Episodic & Causal Memory (${g})`;
        else if (g === 'antigravity_docs') label = '📚 Documentation & Knowledge Graph (antigravity_docs)';
        else if (g.includes('symbol')) label = `⚡ AST Symbol & Call Graph (${g})`;
        return `<option value="${g}">${label}</option>`;
      }).join('');
      if (Array.from(select.options).some(o => o.value === currentVal)) {
        select.value = currentVal;
      }
    }
  } catch (err) {
    console.warn('Could not fetch graphs list:', err);
  }
}

export async function loadGraph() {
  const statsEl = document.getElementById('graph-stats');
  if (statsEl) statsEl.textContent = 'Fetching graph data...';
  const select = document.getElementById('select-graph-type');
  const selectedDb = select ? select.value : 'kortext';
  const isSymbols = selectedDb.includes('symbol') || selectedDb.includes('doc');

  const legendEpisodic = document.getElementById('legend-episodic');
  const legendSymbols = document.getElementById('legend-symbols');
  if (legendEpisodic && legendSymbols) {
    legendEpisodic.classList.toggle('hidden', isSymbols);
    legendSymbols.classList.toggle('hidden', !isSymbols);
  }

  const clean = document.getElementById('toggle-hide-mentions') ? document.getElementById('toggle-hide-mentions').checked : true;
  try {
    const data = await api.getGraph(selectedDb, clean);
    if (data.status !== 'ok') {
      if (statsEl) statsEl.textContent = 'Error: ' + data.message;
      return;
    }

    state.graph.allNodes = data.nodes || [];
    state.graph.allEdges = data.edges || [];
    initRelationshipPalette(state.graph.allEdges);

    const largeBanner = document.getElementById('large-graph-banner');
    if (state.graph.allNodes.length > 250) {
      if (largeBanner) {
        largeBanner.classList.remove('hidden');
        const msg = document.getElementById('large-graph-msg');
        if (msg) msg.textContent = `Large graph (${state.graph.allNodes.length} nodes). Density pruning active to prevent hairballing.`;
      }
      const degSelect = document.getElementById('select-min-degree');
      if (degSelect && degSelect.value === '1') {
        degSelect.value = '2';
        state.graph.minDegreeFilter = 2;
      }
    } else if (largeBanner) {
      largeBanner.classList.add('hidden');
    }

    applyGraphFilters();
  } catch (err) {
    if (statsEl) statsEl.textContent = 'Failed to load graph';
    toast('Error loading graph: ' + err.message, 'error');
  }
}

export function applyGraphFilters() {
  const hideMentions = document.getElementById('toggle-hide-mentions') ? document.getElementById('toggle-hide-mentions').checked : false;
  let filteredEdges = state.graph.allEdges;
  if (hideMentions) filteredEdges = filteredEdges.filter(e => !e.is_mention);

  if (state.graph.activeRelFilters && state.graph.activeRelFilters.size > 0) {
    filteredEdges = filteredEdges.filter(e => state.graph.activeRelFilters.has((e.label || '').toUpperCase().trim()));
  }

  let filteredNodes = state.graph.allNodes;

  if (state.graph.isNeighborhoodIsolated && state.graph.isolatedFocalNodeId) {
    const hopRadius = document.getElementById('select-hop-radius') ? document.getElementById('select-hop-radius').value : '1';
    const neighborList = getNeighborhood(state.graph.isolatedFocalNodeId, hopRadius);
    const neighborSet = new Set(neighborList);
    neighborSet.add(state.graph.isolatedFocalNodeId);

    filteredNodes = filteredNodes.filter(n => neighborSet.has(n.id));
    const visNodeIds = new Set(filteredNodes.map(n => n.id));
    filteredEdges = filteredEdges.filter(e => visNodeIds.has(e.from) && visNodeIds.has(e.to));
    const hopCountEl = document.getElementById('isolation-hop-count');
    if (hopCountEl) hopCountEl.textContent = Math.max(0, filteredNodes.length - 1);
  } else {
    if (state.graph.minDegreeFilter > 1) {
      filteredNodes = filteredNodes.filter(n => (n.degree || 0) >= state.graph.minDegreeFilter);
      const visNodeIds = new Set(filteredNodes.map(n => n.id));
      filteredEdges = filteredEdges.filter(e => visNodeIds.has(e.from) && visNodeIds.has(e.to));
    }
  }

  const statsEl = document.getElementById('graph-stats');
  if (statsEl) {
    statsEl.textContent = `${filteredNodes.length} Visible Nodes • ${filteredEdges.length} Relationships`;
  }
  renderGraph(filteredNodes, filteredEdges);

  if (state.graph.isMacroClustered) {
    setTimeout(() => clusterAllModules(), 250);
  }
}

export function renderGraph(nodesData, edgesData) {
  const container = document.getElementById('network-graph');
  if (!container) return;

  const formattedNodes = nodesData.map(n => {
    let icon = '●';
    let bg = '#0f172a', border = '#38bdf8', hiBg = '#1e293b', hiBorder = '#7dd3fc', fontColor = '#f8fafc';
    let shadowColor = 'rgba(56, 189, 248, 0.25)';

    if (n.group === 'episodic' || n.group === 'decision') {
      icon = '💡'; bg = '#2a1406'; border = '#f97316'; hiBg = '#3d1d09'; hiBorder = '#fb923c'; fontColor = '#fed7aa'; shadowColor = 'rgba(249, 115, 22, 0.35)';
    } else if (n.group === 'task') {
      icon = '📋'; bg = '#06202a'; border = '#0284c7'; hiBg = '#075985'; hiBorder = '#38bdf8'; fontColor = '#e0f2fe'; shadowColor = 'rgba(2, 132, 199, 0.35)';
    } else if (n.group === 'project') {
      icon = '📁'; bg = '#1e1b4b'; border = '#6366f1'; hiBg = '#312e81'; hiBorder = '#818cf8'; fontColor = '#e0e7ff'; shadowColor = 'rgba(99, 102, 241, 0.35)';
    } else if (n.group === 'symbol') {
      icon = '⚡'; bg = '#022c22'; border = '#10b981'; hiBg = '#064e3b'; hiBorder = '#34d399'; fontColor = '#a7f3d0'; shadowColor = 'rgba(16, 185, 129, 0.35)';
    } else if (n.group === 'document') {
      icon = '📄'; bg = '#083344'; border = '#06b6d4'; hiBg = '#164e63'; hiBorder = '#22d3ee'; fontColor = '#cffafe'; shadowColor = 'rgba(6, 182, 212, 0.35)';
    }

    const labelText = n.label || n.id;
    const label = labelText.startsWith(icon) ? labelText : `${icon}  ${labelText}`;

    return {
      id: n.id,
      label,
      full_name: n.full_name || n.id,
      group: n.group,
      cluster_id: n.cluster_id || 'general',
      cluster_name: n.cluster_name || 'General',
      degree: n.degree || 0,
      color: { background: bg, border, highlight: { background: hiBg, border: hiBorder } },
      font: { color: fontColor, face: 'ui-monospace, monospace', size: 11, bold: true },
      shape: 'box',
      shapeProperties: { borderRadius: 6 },
      margin: 8,
      borderWidth: 1.6,
      borderWidthSelected: 2.6,
      shadow: { enabled: true, color: shadowColor, size: 12, x: 0, y: 3 },
    };
  });

  const formattedEdges = formatEdgesNonOverlapping(edgesData);
  state.graph.nodesDataSet = new vis.DataSet(formattedNodes);
  state.graph.edgesDataSet = new vis.DataSet(formattedEdges);

  let options;
  if (state.graph.currentLayoutMode === 'hierarchical-lr') {
    options = {
      layout: { hierarchical: { enabled: true, direction: 'LR', sortMethod: 'directed', levelSeparation: 220, nodeSpacing: 160 } },
      physics: { solver: 'hierarchicalRepulsion', hierarchicalRepulsion: { nodeDistance: 160, springLength: 160 } },
      interaction: { hover: true, tooltipDelay: 150 },
    };
  } else if (state.graph.currentLayoutMode === 'hierarchical-ud') {
    options = {
      layout: { hierarchical: { enabled: true, direction: 'UD', sortMethod: 'directed', levelSeparation: 180, nodeSpacing: 180 } },
      physics: { solver: 'hierarchicalRepulsion', hierarchicalRepulsion: { nodeDistance: 160, springLength: 160 } },
      interaction: { hover: true, tooltipDelay: 150 },
    };
  } else {
    options = {
      physics: {
        solver: 'barnesHut',
        barnesHut: { gravitationalConstant: -18000, centralGravity: 0.08, springLength: 180, springConstant: 0.035, damping: 0.16, avoidOverlap: 1.0 },
        stabilization: { enabled: true, iterations: 140 },
      },
      interaction: { hover: true, tooltipDelay: 150 },
    };
  }

  state.graph.network = new vis.Network(container, { nodes: state.graph.nodesDataSet, edges: state.graph.edgesDataSet }, options);

  state.graph.network.on('stabilizationIterationsDone', () => {
    state.graph.network.setOptions({ physics: { enabled: false } });
    setFreezeState(true);
  });
  setTimeout(() => {
    if (state.graph.network) {
      state.graph.network.setOptions({ physics: { enabled: false } });
      setFreezeState(true);
    }
  }, 1500);

  state.graph.network.on('click', (params) => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      if (state.graph.network.isCluster(nodeId)) {
        openClusterDrawer(nodeId);
        return;
      }
      const node = state.graph.nodesDataSet.get(nodeId);
      focusNode(nodeId);
      openDrawer(node);
    } else {
      resetGraphFocus();
      closeDrawer();
    }
  });

  state.graph.network.on('doubleClick', (params) => {
    if (params.nodes.length === 1) {
      const clickedId = params.nodes[0];
      if (state.graph.network.isCluster(clickedId)) {
        state.graph.network.openCluster(clickedId);
      }
    }
  });
}

// Macro-Clustering with Spacious Layout and 100% Reliable Revert
export function toggleMacroClustering() {
  if (!state.graph.network || !state.graph.nodesDataSet) return;
  state.graph.isMacroClustered = !state.graph.isMacroClustered;
  const btn = document.getElementById('btn-toggle-clustering');
  const label = document.getElementById('label-clustering-status');

  if (state.graph.isMacroClustered) {
    clusterAllModules();
    if (btn) btn.className = 'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-semibold bg-indigo-600 text-white shadow-lg transition';
    if (label) label.textContent = 'Macro View (ON)';
    toast('Macro-clustering enabled (Modules grouped)', 'info');
  } else {
    // 100% Deterministic Revert: re-render unclustered graph
    if (btn) btn.className = 'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-semibold bg-indigo-950/60 text-indigo-300 border border-indigo-500/40 hover:bg-indigo-900/60 transition';
    if (label) label.textContent = 'Macro View';
    applyGraphFilters();
    toast('Macro-clustering disabled (Original view restored)', 'info');
  }
}

export function clusterAllModules() {
  if (!state.graph.network || !state.graph.nodesDataSet) return;
  const allN = state.graph.nodesDataSet.get();
  const clusterGroups = new Map();
  allN.forEach(n => {
    const cid = n.cluster_id || 'general';
    const cname = n.cluster_name || cid;
    if (!clusterGroups.has(cid)) clusterGroups.set(cid, { id: cid, name: cname, count: 0 });
    clusterGroups.get(cid).count++;
  });

  // Spacious physics so macro cluster boxes have breathing room and are not cramped together
  state.graph.network.setOptions({
    physics: {
      enabled: true,
      solver: 'barnesHut',
      barnesHut: { gravitationalConstant: -35000, centralGravity: 0.05, springLength: 280, springConstant: 0.03, damping: 0.2, avoidOverlap: 1.0 },
    },
  });

  clusterGroups.forEach((info, cid) => {
    if (info.count >= 2) {
      state.graph.network.cluster({
        joinCondition: (nodeOptions) => nodeOptions.cluster_id === cid,
        processProperties: (clusterOptions, childNodes) => {
          clusterOptions.label = `📦  ${info.name}\n[${childNodes.length} components]`;
          clusterOptions.title = `<b>Subsystem / Module: ${info.name}</b><br/>Contains ${childNodes.length} components.<br/><i>Double-click to expand</i>`;
          clusterOptions.shape = 'box';
          clusterOptions.margin = 12;
          clusterOptions.color = { background: '#1e1b4b', border: '#818cf8', highlight: { background: '#312e81', border: '#c7d2fe' } };
          clusterOptions.font = { color: '#e0e7ff', face: 'ui-monospace, monospace', size: 12, bold: true, multi: true };
          clusterOptions.borderWidth = 2.5;
          clusterOptions.shadow = { enabled: true, color: 'rgba(129, 140, 248, 0.45)', size: 18 };
          return clusterOptions;
        },
        clusterNodeProperties: { id: 'cluster:' + cid, borderWidth: 2.5, allowSingleNodeCluster: false },
      });
    }
  });

  setTimeout(() => {
    if (state.graph.network) {
      state.graph.network.setOptions({ physics: { enabled: false } });
      setFreezeState(true);
    }
  }, 1200);
}

// Density, Layout, and Freeze Handlers
export function handleMinDegreeChange(val) {
  state.graph.minDegreeFilter = parseInt(val, 10) || 1;
  applyGraphFilters();
}

export function handleLayoutModeChange(val) {
  state.graph.currentLayoutMode = val;
  applyGraphFilters();
}

export function handleToggleClean() {
  loadGraph();
}

export function toggleGraphFreeze() {
  if (!state.graph.network) return;
  state.graph.isPhysicsFrozen = !state.graph.isPhysicsFrozen;
  state.graph.network.setOptions({ physics: { enabled: !state.graph.isPhysicsFrozen } });
  setFreezeState(state.graph.isPhysicsFrozen);
}

export function setFreezeState(frozen) {
  state.graph.isPhysicsFrozen = frozen;
  const label = document.getElementById('label-physics-status');
  const dot = document.getElementById('dot-physics');
  const btn = document.getElementById('btn-toggle-freeze');
  const hudBtn = document.getElementById('btn-hud-freeze');

  if (frozen) {
    if (label) label.innerText = 'HARD-FROZEN (60 FPS)';
    if (dot) dot.className = 'w-2 h-2 rounded-full bg-emerald-400';
    if (btn) btn.className = 'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-semibold bg-emerald-950/60 text-emerald-400 border border-emerald-500/40 hover:bg-emerald-900/60 transition';
    if (hudBtn) hudBtn.innerHTML = '<i data-lucide="snowflake" class="w-3.5 h-3.5"></i> Frozen';
  } else {
    if (label) label.innerText = 'SIMULATING...';
    if (dot) dot.className = 'w-2 h-2 rounded-full bg-amber-400 animate-ping';
    if (btn) btn.className = 'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-semibold bg-amber-950/60 text-amber-400 border border-amber-500/40 hover:bg-amber-900/60 transition';
    if (hudBtn) hudBtn.innerHTML = '<i data-lucide="flame" class="w-3.5 h-3.5 text-amber-400"></i> Simulating';
  }
  if (window.lucide) window.lucide.createIcons();
}

// Neighborhood and Search Handlers
export function getNeighborhood(startNodeId, radius) {
  if (!state.graph.network) return [];
  const r = parseInt(radius, 10) || 1;
  let currentLevel = new Set([startNodeId]);
  const visited = new Set([startNodeId]);

  for (let hop = 0; hop < r; hop++) {
    const nextLevel = new Set();
    for (const nid of currentLevel) {
      const neighbors = state.graph.network.getConnectedNodes(nid) || [];
      for (const neighbor of neighbors) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          nextLevel.add(neighbor);
        }
      }
    }
    currentLevel = nextLevel;
  }
  return Array.from(visited);
}

export function isolateNeighborhood(nodeId) {
  if (!nodeId) return;
  state.graph.isolatedFocalNodeId = nodeId;
  state.graph.isNeighborhoodIsolated = true;
  const banner = document.getElementById('isolation-banner');
  if (banner) {
    banner.classList.remove('hidden');
    const targetLabel = document.getElementById('isolation-target-label');
    if (targetLabel) targetLabel.textContent = nodeId.split('/').pop() || nodeId;
  }
  applyGraphFilters();
}

export function exitNeighborhoodIsolation() {
  state.graph.isNeighborhoodIsolated = false;
  state.graph.isolatedFocalNodeId = null;
  const banner = document.getElementById('isolation-banner');
  if (banner) banner.classList.add('hidden');
  applyGraphFilters();
}

export function dismissLargeGraphBanner() {
  const banner = document.getElementById('large-graph-banner');
  if (banner) banner.classList.add('hidden');
}

export function focusNode(nodeId) {
  state.graph.currentFocusedNodeId = nodeId;
  if (!state.graph.network || !state.graph.nodesDataSet) return;
  const connected = getNeighborhood(nodeId, 1);
  connected.push(nodeId);
  const connectedSet = new Set(connected);

  const nodeUpdates = state.graph.nodesDataSet.get().map(n => ({
    id: n.id,
    opacity: connectedSet.has(n.id) ? 1.0 : 0.12,
  }));
  state.graph.nodesDataSet.update(nodeUpdates);

  const edgeUpdates = state.graph.edgesDataSet.get().map(e => {
    const isConn = connectedSet.has(e.from) && connectedSet.has(e.to);
    return {
      id: e.id,
      color: isConn ? (e.originalColor || e.color) : { color: 'rgba(30, 41, 59, 0.2)' },
      width: isConn ? (e.originalWidth || 1.8) : 1,
    };
  });
  state.graph.edgesDataSet.update(edgeUpdates);
}

export function resetGraphFocus() {
  state.graph.currentFocusedNodeId = null;
  const input = document.getElementById('graph-search');
  if (input) input.value = '';
  if (state.graph.nodesDataSet && state.graph.edgesDataSet) {
    state.graph.nodesDataSet.update(state.graph.nodesDataSet.get().map(n => ({ id: n.id, opacity: 1.0 })));
    state.graph.edgesDataSet.update(state.graph.edgesDataSet.get().map(e => ({ id: e.id, color: e.originalColor || e.color, width: e.originalWidth || 1.8 })));
  }
}

export function updateFocusRadius() {
  if (state.graph.currentFocusedNodeId) focusNode(state.graph.currentFocusedNodeId);
}

export function filterGraphBySearch() {
  const q = document.getElementById('graph-search') ? document.getElementById('graph-search').value.toLowerCase().trim() : '';
  if (!q || !state.graph.nodesDataSet) {
    resetGraphFocus();
    return;
  }
  const match = state.graph.nodesDataSet.get().find(n => (n.full_name || n.id).toLowerCase().includes(q));
  if (match) flyToNode(match.id);
}

export function flyToNode(nodeId) {
  if (!state.graph.network || !state.graph.nodesDataSet) return;
  const targetNode = state.graph.nodesDataSet.get(nodeId);
  if (targetNode) {
    state.graph.network.focus(nodeId, { scale: 1.2, animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
    focusNode(nodeId);
    openDrawer(targetNode);
  }
}

export function zoomGraph(factor) {
  if (!state.graph.network) return;
  state.graph.network.moveTo({ scale: state.graph.network.getScale() * factor, animation: { duration: 300 } });
}

export function fitGraph() {
  if (!state.graph.network) return;
  state.graph.network.fit({ animation: { duration: 400 } });
}

// Companion Sidebar & Palette Delegations
export {
  initRelationshipPalette,
  toggleRelFilter,
  setAllRelFilters,
  applyRelPreset,
  openDrawer,
  closeDrawer,
  openClusterDrawer,
} from './graph_inspector.js';

