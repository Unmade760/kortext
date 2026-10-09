/**
 * Kortext Dashboard - Centralized Reactive State Store
 * Immutability and pub/sub event bus for multi-module communication.
 */

export const state = {
  activeTab: 'graph',
  activeProject: 'all',
  availableProjects: ['all', 'kortext'],

  // Knowledge Graph State
  graph: {
    network: null,
    allNodes: [],
    allEdges: [],
    nodesDataSet: null,
    edgesDataSet: null,
    isMacroClustered: false,
    minDegreeFilter: 1,
    currentLayoutMode: 'physics',
    isNeighborhoodIsolated: false,
    isolatedFocalNodeId: null,
    activeRelFilters: new Set(),
    relCounts: {},
    isPhysicsFrozen: true,
    currentFocusedNodeId: null,
    componentScope: 'all',
    isSubsystemsView: false,
  },

  // Blast-Radius State
  blast: {
    network: null,
    nodesDataSet: null,
    edgesDataSet: null,
    isPhysicsFrozen: true,
  },

  // Task DAG State
  tasks: {
    taskList: [],
    viewMode: 'kanban', // 'kanban' | 'dag' | 'list'
    network: null,
    nodesDataSet: null,
    edgesDataSet: null,
    isPhysicsFrozen: true,
  },

  // Decision Journal State
  journal: {
    allEntries: [],
    selectedCategory: 'all',
    searchQuery: '',
  },

  // Telemetry & Health State
  telemetry: {
    services: [],
    metrics: {},
    watcher: {},
    cache: {},
  },
};

// Simple event bus for decoupled module communication
const listeners = new Map();

export function on(event, callback) {
  if (!listeners.has(event)) {
    listeners.set(event, new Set());
  }
  listeners.get(event).add(callback);
  return () => off(event, callback);
}

export function off(event, callback) {
  if (listeners.has(event)) {
    listeners.get(event).delete(callback);
  }
}

export function emit(event, data) {
  if (listeners.has(event)) {
    listeners.get(event).forEach(cb => {
      try {
        cb(data);
      } catch (err) {
        console.error(`Error in event listener for ${event}:`, err);
      }
    });
  }
}
