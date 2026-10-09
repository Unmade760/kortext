/**
 * Kortext Dashboard - UI Utilities, Modals, Toasts, and Tab Routing
 * Accessible UI management with WCAG AA compliance.
 */

import { state } from './state.js';

export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function formatDate(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    return isNaN(d.getTime()) ? isoStr : d.toLocaleString();
  } catch (_) {
    return isoStr;
  }
}

export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied to clipboard!', 'success');
  } catch (err) {
    console.error('Failed to copy:', err);
    toast('Failed to copy to clipboard', 'error');
  }
}

// Accessible Toast Notification System
export function toast(message, type = 'info', duration = 3500) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none max-w-sm w-full';
    container.setAttribute('aria-live', 'polite');
    document.body.appendChild(container);
  }

  const toastEl = document.createElement('div');
  const typeStyles = {
    success: 'bg-emerald-950 border-emerald-500/60 text-emerald-100 shadow-emerald-950/50',
    error: 'bg-rose-950 border-rose-500/60 text-rose-100 shadow-rose-950/50',
    warning: 'bg-amber-950 border-amber-500/60 text-amber-100 shadow-amber-950/50',
    info: 'bg-indigo-950 border-indigo-500/60 text-indigo-100 shadow-indigo-950/50',
  };

  const icons = {
    success: '✅',
    error: '❌',
    warning: '⚠️',
    info: 'ℹ️',
  };

  toastEl.className = `pointer-events-auto p-3.5 rounded-xl border shadow-xl flex items-start gap-2.5 text-xs font-mono transition-all transform duration-300 opacity-0 translate-y-2 ${typeStyles[type] || typeStyles.info}`;
  toastEl.innerHTML = `
    <span class="text-sm shrink-0">${icons[type] || 'ℹ️'}</span>
    <span class="flex-1 break-words font-medium">${escapeHtml(message)}</span>
    <button class="shrink-0 text-slate-400 hover:text-white ml-1 p-0.5" onclick="this.parentElement.remove()">✕</button>
  `;

  container.appendChild(toastEl);
  requestAnimationFrame(() => {
    toastEl.classList.remove('opacity-0', 'translate-y-2');
  });

  setTimeout(() => {
    toastEl.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toastEl.remove(), 300);
  }, duration);
}

// Modal Helpers with ESC and Backdrop Dismiss
export function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');
    const firstInput = modal.querySelector('input, textarea, button');
    if (firstInput) firstInput.focus();
    if (window.lucide) window.lucide.createIcons();
  }
}

export function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('hidden');
    modal.setAttribute('aria-hidden', 'true');
  }
}

// Global modal dismiss on ESC key or clicking outside content
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.fixed:not(.hidden)').forEach(modal => {
      if (modal.id && (modal.id.includes('modal') || modal.id.includes('dialog'))) {
        closeModal(modal.id);
      }
    });
  }
});

// Tab Switcher Router
export function setTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('border-indigo-500', 'text-indigo-400');
    btn.classList.add('border-transparent', 'text-slate-400');
  });
  document.querySelectorAll('.tab-content').forEach(content => content.classList.add('hidden'));

  const activeBtn = document.getElementById(`tab-btn-${tab}`);
  const activeContent = document.getElementById(`tab-content-${tab}`);
  if (activeBtn) {
    activeBtn.classList.add('border-indigo-500', 'text-indigo-400');
    activeBtn.classList.remove('border-transparent', 'text-slate-400');
  }
  if (activeContent) activeContent.classList.remove('hidden');

  state.activeTab = tab;

  // Dispatch tab-specific loaders via window hooks
  if (tab === 'graph' && window.loadGraph) {
    if (window.populateGraphSelector) {
      window.populateGraphSelector().then(() => {
        if (!state.graph.network) window.loadGraph();
      });
    } else {
      window.loadGraph();
    }
  }
  if (tab === 'blast' && window.initBlastTab) window.initBlastTab();
  if (tab === 'tasks' && window.loadTasks) window.loadTasks();
  if (tab === 'journal' && window.loadJournal) window.loadJournal();
  if (tab === 'health' && window.loadHealth) window.loadHealth();
  if (tab === 'collections' && window.loadCollections) window.loadCollections();
  if (tab === 'retrieval' && window.populateRetrievalCollections) window.populateRetrievalCollections();

  setTimeout(() => {
    if (window.lucide) window.lucide.createIcons();
  }, 50);
}
