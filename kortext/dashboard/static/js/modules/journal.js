/**
 * Decision & Episodic Journal Module
 * Supports the mandatory 8-Category Outcome Taxonomy, full-text search, and Markdown viewing.
 */

import { api } from './api.js';
import { getState, setState } from './state.js';
import { showToast, openModal, escapeHtml, formatDate } from './ui.js';

export const OUTCOME_CATEGORIES = [
  'all',
  'decision',
  'roadmap',
  'implementation',
  'experiment',
  'benchmark',
  'investigation',
  'research',
  'report',
];

export async function loadJournal() {
  const { activeCategory } = getState().journal;
  try {
    const res = await api.getJournal(activeCategory === 'all' ? null : activeCategory);
    if (res.status === 'ok') {
      setState((prev) => ({
        journal: {
          ...prev.journal,
          entries: res.entries || [],
        },
      }));
      renderJournal();
    } else {
      showToast(`Failed to load journal: ${res.message}`, 'error');
    }
  } catch (err) {
    showToast(`Error fetching journal: ${err.message}`, 'error');
  }
}

export function setJournalCategory(category) {
  setState((prev) => ({
    journal: { ...prev.journal, activeCategory: category },
  }));

  // Update button visual
  document.querySelectorAll('.journal-cat-chip').forEach((btn) => {
    if (btn.dataset.category === category) {
      btn.className =
        'journal-cat-chip px-3 py-1 rounded-full text-xs font-mono font-semibold bg-indigo-600 text-white shadow-sm border border-indigo-400';
    } else {
      btn.className =
        'journal-cat-chip px-3 py-1 rounded-full text-xs font-mono font-medium bg-slate-900 text-slate-300 hover:bg-slate-800 border border-slate-700';
    }
  });

  loadJournal();
}

export function renderJournal() {
  const { entries, searchQuery } = getState().journal;
  const container = document.getElementById('journal-entries-container');
  if (!container) return;

  const query = (searchQuery || '').toLowerCase();
  const filtered = entries.filter((e) => {
    if (!query) return true;
    return (
      (e.title && e.title.toLowerCase().includes(query)) ||
      (e.content && e.content.toLowerCase().includes(query)) ||
      (e.category && e.category.toLowerCase().includes(query))
    );
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="p-8 text-center border-2 border-dashed border-slate-800 rounded-xl text-xs text-slate-400 font-mono">
        No journal entries found matching criteria.
      </div>
    `;
    return;
  }

  container.innerHTML = filtered
    .map((e) => {
      const cat = escapeHtml(e.category || 'implementation');
      const title = escapeHtml(e.title || 'Untitled Entry');
      const date = formatDate(e.date || e.timestamp);
      const excerpt = escapeHtml((e.content || '').slice(0, 200));

      return `
      <div 
        class="p-4 rounded-xl bg-slate-900/90 border border-slate-700/80 shadow-md hover:border-indigo-500/80 transition cursor-pointer"
        onclick="window.kortextJournal.viewEntry('${encodeURIComponent(e.path || '')}')"
      >
        <div class="flex items-center justify-between gap-2 mb-1.5">
          <span class="text-[11px] font-mono px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-700/60 font-semibold uppercase">${cat}</span>
          <span class="text-xs font-mono text-slate-400">${date}</span>
        </div>
        <h4 class="text-sm font-bold text-slate-100 mb-1.5">${title}</h4>
        <p class="text-xs text-slate-300 line-clamp-2 leading-relaxed">${excerpt}...</p>
      </div>
    `;
    })
    .join('');
}

export async function viewEntry(encodedPath) {
  const path = decodeURIComponent(encodedPath);
  try {
    const res = await api.getJournalEntry(path);
    if (res.status === 'ok') {
      const modal = document.getElementById('modal-journal-viewer');
      const titleEl = document.getElementById('journal-modal-title');
      const contentEl = document.getElementById('journal-modal-content');

      if (titleEl) titleEl.textContent = res.title || path;
      if (contentEl) contentEl.textContent = res.content || '';

      openModal('modal-journal-viewer');
    } else {
      showToast(`Failed to load entry: ${res.message}`, 'error');
    }
  } catch (err) {
    showToast(`Error viewing entry: ${err.message}`, 'error');
  }
}

export function filterJournalSearch(val) {
  setState((prev) => ({ journal: { ...prev.journal, searchQuery: val } }));
  renderJournal();
}
