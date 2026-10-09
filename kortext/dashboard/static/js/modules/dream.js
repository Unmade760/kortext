/**
 * Hybrid Dream Mode Module
 * Triggers Tier A substrate maintenance and Tier B reflection cycles.
 */

import { api } from './api.js';
import { getState } from './state.js';
import { showToast, openModal, closeModal, escapeHtml } from './ui.js';

export function openDreamModal() {
  openModal('modal-dream-mode');
}

export function closeDreamModal() {
  closeModal('modal-dream-mode');
}

export async function runDreamMode(e) {
  if (e) e.preventDefault();
  const form = document.getElementById('form-dream-mode');
  if (!form) return;

  const { activeProject } = getState();
  const purgeStale = form.elements['purge_stale']?.checked || false;

  const btn = document.getElementById('btn-submit-dream');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="animate-spin">🌀</span> Running Cognitive Dream Cycle...`;
  }

  showToast('Initiating Hybrid Dream Mode...', 'info', 3000);

  try {
    const res = await api.triggerDream({
      project: activeProject === 'all' ? 'kortext' : activeProject,
      purgeStale,
    });

    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Trigger Dream Cycle';
    }

    if (res.status === 'ok') {
      showToast('Cognitive Dream Cycle completed successfully!', 'success');
      closeDreamModal();
      renderDreamReportModal(res.report);
    } else {
      showToast(`Dream mode failed: ${res.message}`, 'error');
    }
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Trigger Dream Cycle';
    }
    showToast(`Error during dream cycle: ${err.message}`, 'error');
  }
}

function renderDreamReportModal(report) {
  if (!report) return;
  const modal = document.getElementById('modal-dream-report');
  const content = document.getElementById('dream-report-content');
  if (!modal || !content) return;

  const pruned = report.pruned_facts ?? 0;
  const clusters = report.subsystems_discovered ?? (report.louvain_communities ?? 0);
  const consolidated = report.consolidated_facts ?? 0;
  const skills = report.distilled_skills ?? 0;

  content.innerHTML = `
    <div class="space-y-4 font-mono text-xs">
      <div class="grid grid-cols-2 gap-3">
        <div class="p-3 rounded-lg bg-slate-900 border border-slate-800">
          <div class="text-slate-400">Synaptic Pruning</div>
          <div class="text-lg font-bold text-amber-400">${pruned} Stale Facts</div>
        </div>
        <div class="p-3 rounded-lg bg-slate-900 border border-slate-800">
          <div class="text-slate-400">Louvain Communities</div>
          <div class="text-lg font-bold text-indigo-400">${clusters} Subsystems</div>
        </div>
        <div class="p-3 rounded-lg bg-slate-900 border border-slate-800">
          <div class="text-slate-400">Macro Consolidations</div>
          <div class="text-lg font-bold text-emerald-400">${consolidated} Facts</div>
        </div>
        <div class="p-3 rounded-lg bg-slate-900 border border-slate-800">
          <div class="text-slate-400">Distilled Skills</div>
          <div class="text-lg font-bold text-cyan-400">${skills} Skills</div>
        </div>
      </div>
      ${
        report.report_markdown
          ? `<pre class="p-3 rounded bg-slate-950 border border-slate-800 text-[11px] text-slate-300 overflow-x-auto whitespace-pre-wrap">${escapeHtml(
              report.report_markdown
            )}</pre>`
          : ''
      }
    </div>
  `;

  openModal('modal-dream-report');
}
