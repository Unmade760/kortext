/**
 * Kortext Dashboard - Cognitive Dream Mode Modal
 * Synaptic pruning, Louvain subsystem clustering, invariant induction, and fact consolidation.
 */

import * as api from './api.js';
import { toast, openModal, closeModal } from './ui.js';

export function openDreamModal() {
  const box = document.getElementById('dream-status-box');
  if (box) {
    box.classList.add('hidden');
    box.innerHTML = '';
  }
  openModal('dream-modal');
}

export function closeDreamModal() {
  closeModal('dream-modal');
}

export async function runDreamMode() {
  const btn = document.getElementById('btn-run-dream');
  const statusBox = document.getElementById('dream-status-box');
  const projectInput = document.getElementById('dream-project');
  const purgeCheckbox = document.getElementById('dream-purge-stale');

  const project = projectInput ? projectInput.value.trim() || 'kortext' : 'kortext';
  const purgeStale = purgeCheckbox ? purgeCheckbox.checked : false;

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="animate-spin mr-1">⏳</span> Consolidating...';
  }
  if (statusBox) {
    statusBox.classList.remove('hidden');
    statusBox.innerHTML = '<div class="text-purple-400 font-mono text-xs">🌙 Executing consolidation cycle (Pruning, Louvain clustering, Invariant induction)...</div>';
  }

  try {
    const data = await api.runDream(project, purgeStale);
    if (data.status === 'ok') {
      const r = data.report || {};
      const pruned = r.pruned_facts || {};
      if (statusBox) {
        statusBox.innerHTML = `
          <div class="text-emerald-400 font-bold font-mono text-xs">✅ Dream Mode completed successfully!</div>
          <div class="space-y-1 text-slate-300 font-mono text-xs pt-1">
            <div>• Active Facts Remaining: <span class="text-indigo-400 font-bold">${pruned.active_facts_remaining !== undefined ? pruned.active_facts_remaining : 'N/A'}</span></div>
            <div>• Superseded Facts Pruned: <span class="text-amber-400 font-bold">${pruned.superseded_facts_pruned !== undefined ? pruned.superseded_facts_pruned : '0'}</span></div>
            <div>• Contradictions Flagged: <span class="text-rose-400 font-bold">${(pruned.contradictions_flagged || []).length}</span></div>
            <div>• Subsystem Clusters: <span class="text-sky-400 font-bold">${r.subsystem_clusters || 'N/A'}</span></div>
            <div>• Invariant Rules: <span class="text-emerald-400 font-bold">${r.invariants_inducted || 'N/A'}</span></div>
            ${r.dream_report_path ? `<div class="text-slate-400 pt-1 text-[10px]">Report: ${r.dream_report_path}</div>` : ''}
          </div>
        `;
      }
      toast('Dream consolidation complete!', 'success');
      if (window.loadGraph) window.loadGraph();
    } else {
      if (statusBox) statusBox.innerHTML = `<div class="text-rose-400 font-bold font-mono text-xs">❌ Error: ${data.message}</div>`;
      toast('Dream mode failed: ' + data.message, 'error');
    }
  } catch (err) {
    if (statusBox) statusBox.innerHTML = `<div class="text-rose-400 font-bold font-mono text-xs">❌ Failed: ${err.message}</div>`;
    toast('Dream mode error: ' + err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i data-lucide="sparkles" class="w-3.5 h-3.5"></i> Run Dream Mode';
      if (window.lucide) window.lucide.createIcons();
    }
  }
}
