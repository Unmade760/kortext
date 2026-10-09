/**
 * Main Application Entry Point
 * Orchestrates ES module imports, DOM event binding, and global backward-compatibility shims.
 */

import { getState, setState, on } from './modules/state.js';
import { api } from './modules/api.js';
import { showToast, setTab, openModal, closeModal, escapeHtml } from './modules/ui.js';
import {
  initTelemetry,
  loadAllTelemetry,
  clearChunkCache,
} from './modules/telemetry.js';
import {
  loadTasks,
  setTaskViewMode,
  updateTaskStatus,
  submitCreateTask,
  openCreateTaskModal,
  onProjectFilterChange,
} from './modules/kanban.js';
import {
  loadGraph,
  populateGraphSelector,
  toggleMacroClustering,
  toggleNeighborhoodIsolation,
  toggleGraphFreeze,
  handleMinDegreeChange,
  toggleRelFilter,
  zoomGraph,
  fitGraph,
  closeDrawer,
} from './modules/graph.js';
import {
  initBlastTab,
  executeBlastAnalysis,
  zoomBlastGraph,
  fitBlastGraph,
} from './modules/blast.js';
import {
  loadJournal,
  setJournalCategory,
  viewEntry,
  filterJournalSearch,
} from './modules/journal.js';
import {
  populateRetrievalCollections,
  executeRetrieval,
} from './modules/retrieval.js';
import {
  openDreamModal,
  closeDreamModal,
  runDreamMode,
} from './modules/dream.js';

// Global Backward-Compatibility Window Shims
window.setTab = (tab) => {
  setTab(tab);
  if (tab === 'graph') loadGraph();
  if (tab === 'tasks') loadTasks();
  if (tab === 'blast') initBlastTab();
  if (tab === 'journal') loadJournal();
  if (tab === 'health') loadAllTelemetry();
  if (tab === 'retrieval') populateRetrievalCollections();
};

window.refreshAll = () => {
  showToast('Refreshing dashboard telemetry and views...', 'info', 1500);
  loadAllTelemetry();
  const currentTab = getState().activeTab;
  if (currentTab === 'graph') loadGraph();
  if (currentTab === 'tasks') loadTasks();
  if (currentTab === 'journal') loadJournal();
};

window.loadGraph = loadGraph;
window.loadTasks = loadTasks;
window.clearChunkCache = clearChunkCache;
window.openDreamModal = openDreamModal;
window.closeDreamModal = closeDreamModal;
window.runDreamMode = runDreamMode;
window.openCreateTaskModal = openCreateTaskModal;
window.closeCreateTaskModal = () => closeModal('modal-create-task');
window.submitCreateTask = submitCreateTask;
window.zoomGraph = zoomGraph;
window.fitGraph = fitGraph;
window.closeDrawer = closeDrawer;
window.zoomBlastGraph = zoomBlastGraph;
window.fitBlastGraph = fitBlastGraph;

// Domain Namespace Shims
window.kortextKanban = {
  setTaskViewMode,
  quickAdvance: (taskId, nextStatus) => updateTaskStatus(taskId, nextStatus),
  onProjectFilterChange,
};

window.kortextGraph = {
  toggleMacroClustering,
  toggleNeighborhoodIsolation,
  toggleGraphFreeze,
  handleMinDegreeChange,
  toggleRelFilter,
};

window.kortextBlast = {
  executeBlastAnalysis,
};

window.kortextJournal = {
  setCategory: setJournalCategory,
  viewEntry,
  filterSearch: filterJournalSearch,
};

window.kortextRetrieval = {
  executeRetrieval,
};

// Bootstrap on DOM Ready
document.addEventListener('DOMContentLoaded', async () => {
  console.log('🧠 [Kortext Dashboard v1] Initializing Modular ES Core...');

  // Initialize Lucide icons
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }

  // Load telemetry and initial view
  await initTelemetry();
  await populateGraphSelector();
  setTab('graph');
  await loadGraph();

  // Bind project switcher in header if present
  const headerProjSelect = document.getElementById('select-header-project');
  if (headerProjSelect) {
    headerProjSelect.addEventListener('change', (e) => {
      setState({ activeProject: e.target.value });
      window.refreshAll();
    });
  }
});
