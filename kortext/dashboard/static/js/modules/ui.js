/**
 * UI & Accessibility Module
 * High-contrast toast system, modal manager, tab switching, and formatting utilities.
 */

import { getState, setState } from './state.js';

// Toast Notification System (WCAG AA High-Contrast)
export function showToast(message, type = 'info', duration = 3500) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-sm pointer-events-none';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  const typeStyles = {
    success: 'bg-emerald-950 border-emerald-500 text-emerald-200 shadow-emerald-950/50',
    error: 'bg-rose-950 border-rose-500 text-rose-200 shadow-rose-950/50',
    warning: 'bg-amber-950 border-amber-500 text-amber-200 shadow-amber-950/50',
    info: 'bg-slate-900 border-indigo-500 text-slate-100 shadow-indigo-950/50',
  };

  const icons = {
    success: '✓',
    error: '✕',
    warning: '⚠',
    info: 'ℹ',
  };

  toast.className = `pointer-events-auto flex items-start gap-3 p-3.5 rounded-lg border shadow-xl text-xs font-mono transition-all transform duration-200 translate-y-2 opacity-0 ${typeStyles[type] || typeStyles.info}`;
  toast.innerHTML = `
    <span class="font-bold text-sm leading-none">${icons[type] || '•'}</span>
    <div class="flex-1 break-words">${escapeHtml(message)}</div>
    <button class="opacity-60 hover:opacity-100 transition text-sm leading-none font-bold" aria-label="Close">&times;</button>
  `;

  const closeBtn = toast.querySelector('button');
  const dismiss = () => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 200);
  };
  closeBtn.addEventListener('click', dismiss);

  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.remove('opacity-0', 'translate-y-2'));

  if (duration > 0) {
    setTimeout(dismiss, duration);
  }
}

// Modal Management
export function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.remove('hidden');
  modal.classList.add('flex');
  document.body.classList.add('overflow-hidden');

  // Focus trap first input
  const firstInput = modal.querySelector('input, select, textarea, button');
  if (firstInput) setTimeout(() => firstInput.focus(), 50);
}

export function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.add('hidden');
  modal.classList.remove('flex');
  document.body.classList.remove('overflow-hidden');
}

// Global modal backdrop and ESC listener
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop:not(.hidden)').forEach((m) => {
      closeModal(m.id);
    });
  }
});

// Tab Navigation
export function setTab(tabName) {
  setState({ activeTab: tabName });

  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.classList.remove('border-indigo-400', 'text-indigo-300', 'bg-slate-800/40');
    btn.classList.add('border-transparent', 'text-slate-300');
  });

  document.querySelectorAll('.tab-content').forEach((content) => {
    content.classList.add('hidden');
  });

  const activeBtn = document.getElementById(`tab-btn-${tabName}`);
  const activeContent = document.getElementById(`tab-content-${tabName}`);

  if (activeBtn) {
    activeBtn.classList.add('border-indigo-400', 'text-indigo-300', 'bg-slate-800/40');
    activeBtn.classList.remove('border-transparent', 'text-slate-300');
  }
  if (activeContent) {
    activeContent.classList.remove('hidden');
  }

  // Refresh icons
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    setTimeout(() => window.lucide.createIcons(), 30);
  }
}

// HTML Escaping Utility
export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Relative/Absolute Date Formatter
export function formatDate(timestamp) {
  if (!timestamp) return '—';
  try {
    const d = new Date(typeof timestamp === 'number' && timestamp < 1e12 ? timestamp * 1000 : timestamp);
    if (isNaN(d.getTime())) return String(timestamp);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (_) {
    return String(timestamp);
  }
}

// Clipboard Copy
export async function copyToClipboard(text, successMessage = 'Copied to clipboard!') {
  try {
    await navigator.clipboard.writeText(text);
    showToast(successMessage, 'success', 2000);
  } catch (err) {
    showToast(`Failed to copy: ${err.message}`, 'error');
  }
}
