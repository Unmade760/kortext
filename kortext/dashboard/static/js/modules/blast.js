/**
 * Blast-Radius & Symbol Impact Explorer Module
 * Upstream/downstream AST impact graphs, risk scores, and caller tree hierarchy.
 */

import { api } from './api.js';
import { getState, setState } from './state.js';
import { showToast, escapeHtml } from './ui.js';

let blastNetwork = null;
let blastNodesDataSet = null;
let blastEdgesDataSet = null;

export function initBlastTab() {
  const input = document.getElementById('blast-target-input');
  if (input && !input.value) {
    input.value = 'kortext.server';
  }
}

export async function executeBlastAnalysis() {
  const input = document.getElementById('blast-target-input');
  const target = input ? input.value.trim() : '';
  const dirSelect = document.getElementById('blast-direction-select');
  const direction = dirSelect ? dirSelect.value : 'upstream';
  const depthInput = document.getElementById('blast-depth-input');
  const maxDepth = depthInput ? parseInt(depthInput.value, 10) : 3;

  if (!target) {
    showToast('Please enter a symbol or file path to analyze', 'warning');
    return;
  }

  showToast(`Tracing ${direction} impact for ${target}...`, 'info', 1500);

  try {
    const res = await api.getSymbolImpact({
      target,
      direction,
      maxDepth,
    });

    if (res.status === 'ok') {
      setState((prev) => ({
        blast: {
          ...prev.blast,
          target,
          direction,
          maxDepth,
          data: res,
        },
      }));

      renderBlastMetrics(res);
      renderBlastGraph(res.nodes || [], res.edges || []);
      renderBlastTree(res.tree || []);
    } else {
      showToast(`Blast analysis failed: ${res.message}`, 'error');
    }
  } catch (err) {
    showToast(`Error analyzing blast radius: ${err.message}`, 'error');
  }
}

function renderBlastMetrics(data) {
  const riskBadge = document.getElementById('blast-risk-badge');
  const nodeCount = document.getElementById('blast-affected-nodes');
  const edgeCount = document.getElementById('blast-affected-edges');

  const count = (data.nodes || []).length;
  if (nodeCount) nodeCount.textContent = count;
  if (edgeCount) edgeCount.textContent = (data.edges || []).length;

  if (riskBadge) {
    const risk = count > 15 ? 'HIGH RISK' : count > 5 ? 'MEDIUM RISK' : 'LOW RISK';
    const color =
      count > 15
        ? 'bg-rose-950 text-rose-300 border-rose-600'
        : count > 5
        ? 'bg-amber-950 text-amber-300 border-amber-600'
        : 'bg-emerald-950 text-emerald-300 border-emerald-600';
    riskBadge.className = `px-2.5 py-1 rounded border text-xs font-mono font-bold ${color}`;
    riskBadge.textContent = risk;
  }
}

function renderBlastGraph(nodes, edges) {
  const container = document.getElementById('blast-network-graph');
  if (!container || !window.vis) return;

  const target = getState().blast.target;

  const visNodes = nodes.map((n) => {
    const isTarget = n.id === target || (n.label && n.label.includes(target));
    return {
      id: n.id,
      label: n.label || n.id,
      color: isTarget
        ? { background: '#ef4444', border: '#ffffff' }
        : { background: '#6366f1', border: '#cbd5e1' },
      font: { color: '#ffffff', size: 11, face: 'monospace', bold: isTarget },
      shape: isTarget ? 'box' : 'dot',
      size: isTarget ? 25 : 15,
    };
  });

  const visEdges = edges.map((e) => ({
    from: e.from,
    to: e.to,
    arrows: 'to',
    color: { color: '#94a3b8' },
  }));

  blastNodesDataSet = new window.vis.DataSet(visNodes);
  blastEdgesDataSet = new window.vis.DataSet(visEdges);

  const options = {
    layout: {
      hierarchical: {
        direction: getState().blast.direction === 'upstream' ? 'UD' : 'DU',
        sortMethod: 'directed',
        levelSeparation: 120,
      },
    },
    physics: false,
    interaction: { hover: true, tooltipDelay: 100 },
  };

  if (blastNetwork) blastNetwork.destroy();
  blastNetwork = new window.vis.Network(container, { nodes: blastNodesDataSet, edges: blastEdgesDataSet }, options);
}

function renderBlastTree(treeNodes) {
  const container = document.getElementById('blast-tree-container');
  if (!container) return;

  if (!treeNodes || treeNodes.length === 0) {
    container.innerHTML = '<div class="text-xs text-slate-400 font-mono p-4">No callers or dependencies found.</div>';
    return;
  }

  container.innerHTML = `
    <ul class="space-y-1 text-xs font-mono">
      ${treeNodes
        .map(
          (item) => `
        <li class="p-2 rounded bg-slate-900 border border-slate-800 flex items-center justify-between">
          <span class="text-slate-200">${escapeHtml(item.name || item.id)}</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">${escapeHtml(
            item.relation || 'CALLS'
          )}</span>
        </li>
      `
        )
        .join('')}
    </ul>
  `;
}

export function zoomBlastGraph(delta) {
  if (!blastNetwork) return;
  const scale = blastNetwork.getScale() + delta;
  blastNetwork.moveTo({ scale: Math.max(0.1, Math.min(3, scale)) });
}

export function fitBlastGraph() {
  if (blastNetwork) blastNetwork.fit({ animation: { duration: 400 } });
}
