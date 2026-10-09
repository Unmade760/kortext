/**
 * State Management Module
 * Centralized, immutable reactive state store for Kortext Dashboard.
 */

const listeners = new Map();

const initialState = Object.freeze({
  activeTab: 'graph',
  activeProject: 'kortext',
  availableProjects: ['all', 'kortext'],
  services: [],
  telemetry: null,
  watcher: null,
  cacheStats: null,
  graph: {
    type: 'episodic',
    currentName: null,
    availableGraphs: [],
    clean: true,
    minDegree: 0,
    clusterMode: 'none', // 'none' | 'module' | 'subsystem'
    isFrozen: false,
    selectedNodeId: null,
    isolatedNeighborhood: false,
    activeRelations: new Set(),
    allRelations: new Set(),
  },
  blast: {
    target: '',
    direction: 'upstream',
    maxDepth: 3,
    data: null,
    isFrozen: false,
  },
  tasks: {
    list: [],
    readyList: [],
    viewMode: 'kanban', // 'kanban' | 'graph'
    selectedTaskId: null,
    isFrozen: false,
  },
  journal: {
    entries: [],
    selectedEntry: null,
    activeCategory: 'all',
    searchQuery: '',
  },
  retrieval: {
    collections: [],
    selectedCollection: null,
    lastResults: null,
    isSearching: false,
  },
});

let currentState = { ...initialState };

export function getState() {
  return currentState;
}

export function setState(patch) {
  const prevState = currentState;
  const nextState = Object.freeze({
    ...prevState,
    ...(typeof patch === 'function' ? patch(prevState) : patch),
  });
  currentState = nextState;
  emit('stateChange', { prevState, nextState });
}

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
    listeners.get(event).forEach((cb) => {
      try {
        cb(data);
      } catch (err) {
        console.error(`[State Error] Listener failed for event '${event}':`, err);
      }
    });
  }
}
