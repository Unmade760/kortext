/**
 * Task DAG & Interactive Kanban Module
 * Full drag-and-drop Kanban board, Vis.js dependency graph, project filter, and task manager.
 */

import { api } from './api.js';
import { getState, setState } from './state.js';
import { showToast, openModal, closeModal, escapeHtml } from './ui.js';

let taskNetwork = null;
let taskNodesDataSet = null;
let taskEdgesDataSet = null;

const STATUS_CONFIG = {
  ready: {
    label: 'Ready to Execute',
    color: '#10b981', // Emerald
    bgClass: 'bg-emerald-950/40 border-emerald-500/40',
    headerBadge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  },
  in_progress: {
    label: 'In Progress',
    color: '#3b82f6', // Blue
    bgClass: 'bg-blue-950/40 border-blue-500/40',
    headerBadge: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  },
  pending: {
    label: 'Pending / Blocked',
    color: '#94a3b8', // Slate
    bgClass: 'bg-slate-900/60 border-slate-700/60',
    headerBadge: 'bg-slate-800 text-slate-300 border-slate-700',
  },
  completed: {
    label: 'Completed & Verified',
    color: '#8b5cf6', // Violet
    bgClass: 'bg-indigo-950/40 border-indigo-500/40',
    headerBadge: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
  },
  failed: {
    label: 'Failed / Circuit Breaker',
    color: '#ef4444', // Red
    bgClass: 'bg-rose-950/40 border-rose-500/40',
    headerBadge: 'bg-rose-500/20 text-rose-300 border-rose-500/30',
  },
};

export async function loadTasks() {
  const { activeProject } = getState();
  try {
    const res = await api.getTasks(activeProject === 'all' ? null : activeProject);
    if (res.status === 'ok') {
      setState((prev) => ({
        tasks: {
          ...prev.tasks,
          list: res.tasks || [],
          readyList: res.ready_tasks || [],
        },
        availableProjects: res.projects && res.projects.length ? res.projects : prev.availableProjects,
      }));

      updateProjectDropdown(res.projects || ['all', 'kortext']);
      renderKanbanBoard();
      if (getState().tasks.viewMode === 'graph') {
        renderTaskGraph(res.nodes || [], res.edges || []);
      }
    } else {
      showToast(`Failed to load tasks: ${res.message}`, 'error');
    }
  } catch (err) {
    showToast(`Error fetching Task DAG: ${err.message}`, 'error');
  }
}

export function setTaskViewMode(mode) {
  setState((prev) => ({ tasks: { ...prev.tasks, viewMode: mode } }));
  const btnKanban = document.getElementById('btn-view-kanban');
  const btnGraph = document.getElementById('btn-view-graph');
  const boardEl = document.getElementById('kanban-board-container');
  const graphEl = document.getElementById('task-graph-container');

  if (mode === 'kanban') {
    if (btnKanban) btnKanban.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow';
    if (btnGraph) btnGraph.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-300 hover:bg-slate-700';
    if (boardEl) boardEl.classList.remove('hidden');
    if (graphEl) graphEl.classList.add('hidden');
    renderKanbanBoard();
  } else {
    if (btnKanban) btnKanban.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-300 hover:bg-slate-700';
    if (btnGraph) btnGraph.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow';
    if (boardEl) boardEl.classList.add('hidden');
    if (graphEl) graphEl.classList.remove('hidden');
    loadTasks();
  }
}

export function updateProjectDropdown(projects) {
  const select = document.getElementById('select-task-project');
  if (!select) return;
  const current = getState().activeProject;
  select.innerHTML = ['all', ...projects.filter((p) => p !== 'all')]
    .map((p) => `<option value="${escapeHtml(p)}" ${p === current ? 'selected' : ''}>${p === 'all' ? 'All Projects' : p}</option>`)
    .join('');
}

export function onProjectFilterChange(projectId) {
  setState({ activeProject: projectId });
  loadTasks();
}

export function renderKanbanBoard() {
  const { tasks } = getState();
  const allTasks = tasks.list || [];

  // Group tasks by status
  const columns = {
    ready: [],
    in_progress: [],
    pending: [],
    completed: [],
    failed: [],
  };

  allTasks.forEach((t) => {
    const st = (t.status || 'pending').toLowerCase();
    if (columns[st]) {
      columns[st].push(t);
    } else {
      columns.pending.push(t);
    }
  });

  Object.keys(columns).forEach((statusKey) => {
    const countEl = document.getElementById(`count-${statusKey}`);
    if (countEl) countEl.textContent = columns[statusKey].length;

    const columnBody = document.getElementById(`column-${statusKey}`);
    if (!columnBody) return;

    if (columns[statusKey].length === 0) {
      columnBody.innerHTML = `
        <div class="h-32 flex items-center justify-center border-2 border-dashed border-slate-800/80 rounded-xl text-xs text-slate-400 font-mono">
          No tasks in this lane
        </div>
      `;
      setupDropZone(columnBody, statusKey);
      return;
    }

    columnBody.innerHTML = columns[statusKey]
      .map((t) => renderTaskCard(t))
      .join('');

    setupDropZone(columnBody, statusKey);
  });

  // Attach card drag events
  document.querySelectorAll('.kanban-card').forEach((card) => {
    card.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/plain', card.dataset.taskId);
      e.dataTransfer.effectAllowed = 'move';
      card.classList.add('opacity-40', 'scale-95');
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('opacity-40', 'scale-95');
    });
  });
}

function setupDropZone(columnEl, targetStatus) {
  columnEl.ondragover = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    columnEl.classList.add('bg-slate-800/30');
  };
  columnEl.ondragleave = () => {
    columnEl.classList.remove('bg-slate-800/30');
  };
  columnEl.ondrop = async (e) => {
    e.preventDefault();
    columnEl.classList.remove('bg-slate-800/30');
    const taskId = e.dataTransfer.getData('text/plain');
    if (taskId) {
      await updateTaskStatus(taskId, targetStatus);
    }
  };
}

function renderTaskCard(task) {
  const tid = escapeHtml(task.id);
  const title = escapeHtml(task.title || 'Untitled Task');
  const complexity = task.complexity || 1;
  const assigned = escapeHtml(task.assigned_to || 'primary');
  const currentStatus = (task.status || 'pending').toLowerCase();
  const nextStatus = currentStatus === 'ready' ? 'in_progress' : currentStatus === 'in_progress' ? 'completed' : null;

  return `
    <div 
      class="kanban-card p-3.5 rounded-xl bg-slate-900/90 border border-slate-700/80 shadow-md hover:border-slate-500 hover:shadow-lg transition-all cursor-grab active:cursor-grabbing mb-3"
      draggable="true"
      data-task-id="${tid}"
    >
      <div class="flex items-center justify-between gap-2 mb-2">
        <span class="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-950 text-indigo-300 border border-indigo-800/60 font-semibold">${tid}</span>
        <div class="flex items-center gap-1.5">
          <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-600/40 font-bold" title="Complexity Score">C: ${complexity}</span>
          <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-600/40">${assigned}</span>
        </div>
      </div>
      <h4 class="text-xs font-semibold text-slate-100 leading-snug mb-2">${title}</h4>
      ${
        task.description
          ? `<p class="text-[11px] text-slate-300 line-clamp-2 mb-2 leading-relaxed">${escapeHtml(task.description)}</p>`
          : ''
      }
      <div class="flex items-center justify-between pt-2 border-t border-slate-800/80 text-[11px] font-mono">
        <span class="text-slate-400 truncate max-w-[120px]">${escapeHtml(task.project_id || 'kortext')}</span>
        ${
          nextStatus
            ? `<button 
                onclick="window.kortextKanban.quickAdvance('${tid}', '${nextStatus}')"
                class="px-2 py-0.5 rounded bg-indigo-950 hover:bg-indigo-900 text-indigo-300 border border-indigo-700/60 text-[10px] font-semibold transition"
               >
                 Move &rarr; ${nextStatus}
               </button>`
            : ''
        }
      </div>
    </div>
  `;
}

export async function updateTaskStatus(taskId, status, error = null) {
  try {
    const res = await api.manageTask({
      action: 'update_status',
      task_id: taskId,
      status,
      error,
    });
    if (res.status === 'ok') {
      showToast(`Task ${taskId} moved to ${status}`, 'success', 2000);
      await loadTasks();
    } else {
      showToast(`Status update failed: ${res.message}`, 'error');
    }
  } catch (err) {
    showToast(`Error updating task: ${err.message}`, 'error');
  }
}

export async function submitCreateTask(e) {
  if (e) e.preventDefault();
  const form = document.getElementById('form-create-task');
  if (!form) return;

  const title = form.elements['title']?.value?.trim();
  const description = form.elements['description']?.value?.trim() || '';
  const project_id = form.elements['project_id']?.value?.trim() || 'kortext';
  const complexity = parseInt(form.elements['complexity']?.value || '1', 10);
  const assigned_to = form.elements['assigned_to']?.value || 'primary';
  const dependsOnSelect = form.elements['depends_on'];
  const depends_on = dependsOnSelect
    ? Array.from(dependsOnSelect.selectedOptions).map((o) => o.value)
    : [];

  if (!title) {
    showToast('Task title is required', 'warning');
    return;
  }

  try {
    const res = await api.manageTask({
      action: 'create',
      title,
      description,
      project_id,
      complexity,
      assigned_to,
      depends_on: depends_on.length ? depends_on : null,
    });

    if (res.status === 'ok') {
      showToast(`Task created: ${res.task_id}`, 'success');
      closeModal('modal-create-task');
      form.reset();
      await loadTasks();
    } else {
      showToast(`Task creation failed: ${res.message}`, 'error');
    }
  } catch (err) {
    showToast(`Error creating task: ${err.message}`, 'error');
  }
}

export function openCreateTaskModal() {
  const { tasks } = getState();
  const dependsOnSelect = document.getElementById('task-input-depends');
  if (dependsOnSelect) {
    dependsOnSelect.innerHTML = (tasks.list || [])
      .map((t) => `<option value="${escapeHtml(t.id)}">${escapeHtml(t.id)}: ${escapeHtml(t.title)}</option>`)
      .join('');
  }
  openModal('modal-create-task');
}

export function renderTaskGraph(nodes, edges) {
  const container = document.getElementById('task-network-graph');
  if (!container || !window.vis) return;

  const visNodes = nodes.map((n) => {
    const st = (n.status || 'pending').toLowerCase();
    const cfg = STATUS_CONFIG[st] || STATUS_CONFIG.pending;
    return {
      id: n.id,
      label: n.title || n.id,
      color: {
        background: cfg.color,
        border: '#ffffff',
        highlight: { background: cfg.color, border: '#ffffff' },
      },
      font: { color: '#ffffff', size: 12, face: 'monospace', bold: true },
      shape: 'box',
      margin: 10,
    };
  });

  const visEdges = edges.map((e) => ({
    from: e.from,
    to: e.to,
    arrows: 'to',
    color: { color: '#64748b', highlight: '#6366f1' },
    dashes: true,
  }));

  taskNodesDataSet = new window.vis.DataSet(visNodes);
  taskEdgesDataSet = new window.vis.DataSet(visEdges);

  const options = {
    layout: {
      hierarchical: {
        direction: 'LR',
        sortMethod: 'directed',
        levelSeparation: 160,
        nodeSpacing: 80,
      },
    },
    physics: false,
    interaction: { hover: true, tooltipDelay: 100 },
  };

  if (taskNetwork) taskNetwork.destroy();
  taskNetwork = new window.vis.Network(container, { nodes: taskNodesDataSet, edges: taskEdgesDataSet }, options);
}
