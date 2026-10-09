    let network = null;
    let allNodes = [];
    let allEdges = [];
    let nodesDataSet = null;
    let edgesDataSet = null;
    let allJournalEntries = [];
    let blastNetwork = null;
    let blastNodesDataSet = null;
    let blastEdgesDataSet = null;

    function setTab(tab) {
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

      if (tab === 'graph') {
        populateGraphSelector().then(() => { if (!network) loadGraph(); });
      }
      if (tab === 'blast') initBlastTab();
      if (tab === 'tasks') loadTasks();
      if (tab === 'journal') loadJournal();
      if (tab === 'quarantine') loadQuarantine();
      if (tab === 'health') loadHealth();
      if (tab === 'collections') loadCollections();
      if (tab === 'retrieval') populateRetrievalCollections();
      setTimeout(() => lucide.createIcons(), 50);
    }

    async function loadHealth() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        updateQuickPills(data.services);
      } catch (e) {
        console.error("Health check error:", e);
      }
      loadTelemetry();

      // Fetch Watcher Status
      try {
        const wRes = await fetch('/api/watcher/status');
        const wData = await wRes.json();
        if (wData.status === 'ok' && wData.watcher) {
          updateWatcherUI(wData.watcher);
        }
      } catch (e) {
        console.error("Watcher status error:", e);
      }

      // Fetch Cache Stats
      try {
        const cRes = await fetch('/api/cache/stats');
        const cData = await cRes.json();
        if (cData.status === 'ok') {
          updateCacheUI(cData);
        }
      } catch (e) {
        console.error("Cache stats error:", e);
      }

      lucide.createIcons();
    }

    function updateQuickPills(services) {
      services.forEach(s => {
        const id = s.name.toLowerCase().includes('qdrant') ? 'pill-qdrant'
                 : s.name.toLowerCase().includes('falkordb graph') ? 'pill-falkordb'
                 : s.name.toLowerCase().includes('omlx') ? 'pill-omlx' : null;
        if (id) {
          const el = document.getElementById(id);
          if (el) {
            el.className = s.healthy 
              ? 'px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/50 flex items-center gap-1.5'
              : 'px-2 py-0.5 rounded bg-rose-950/80 text-rose-400 border border-rose-800/50 flex items-center gap-1.5';
            el.innerHTML = `<span class="w-1.5 h-1.5 rounded-full ${s.healthy ? 'bg-emerald-400' : 'bg-rose-400'}"></span> ${s.name.split(' ')[0]}`;
          }
        }
      });
    }

    function updateWatcherUI(w) {
      const isRunning = w.running && w.alive !== false;
      const pill = document.getElementById('pill-watcher');
      if (pill) {
        pill.className = isRunning
          ? 'px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/50 flex items-center gap-1.5'
          : 'px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 flex items-center gap-1.5';
        pill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-emerald-400' : 'bg-slate-500'}"></span> Watcher: ${isRunning ? 'ON' : 'OFF'}`;
      }

      const badge = document.getElementById('watcher-status-badge');
      if (badge) {
        badge.className = isRunning
          ? 'text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-bold'
          : 'text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700';
        badge.textContent = isRunning ? 'RUNNING' : 'STOPPED';
      }

      if (document.getElementById('watcher-root')) document.getElementById('watcher-root').textContent = w.root || '-';
      if (document.getElementById('watcher-debounce')) document.getElementById('watcher-debounce').textContent = (w.debounce_sec || 2.0) + 's';
      if (document.getElementById('watcher-processed')) document.getElementById('watcher-processed').textContent = (w.total_processed || 0).toLocaleString();
      if (document.getElementById('watcher-pending')) document.getElementById('watcher-pending').textContent = (w.pending_count || 0).toLocaleString();
      if (document.getElementById('watcher-last-file')) {
        const lf = w.last_synced_file ? w.last_synced_file.split('/').slice(-2).join('/') : '-';
        document.getElementById('watcher-last-file').textContent = lf;
        document.getElementById('watcher-last-file').title = w.last_synced_file || '';
      }
    }

    function updateCacheUI(c) {
      const cc = c.chunk_cache || {};
      if (document.getElementById('cache-chunks-count')) {
        document.getElementById('cache-chunks-count').textContent = (cc.total_cached_chunks || 0).toLocaleString();
      }
      if (document.getElementById('cache-size-mb')) {
        document.getElementById('cache-size-mb').textContent = `${cc.storage_size_mb || 0} MB`;
      }
      if (document.getElementById('cache-indexed-files')) {
        document.getElementById('cache-indexed-files').textContent = (c.total_indexed_files || 0).toLocaleString();
      }
    }

    async function clearChunkCache() {
      if (!confirm("Are you sure you want to clear the Chunk Embedding Cache? Sub-second incremental caching will reset.")) return;
      try {
        const res = await fetch('/api/cache/clear', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
          alert(`✅ Purged ${data.purged_chunks} cached chunk vectors.`);
          loadHealth();
        } else {
          alert(`Error clearing cache: ${data.message}`);
        }
      } catch (e) {
        alert("Cache clear failed: " + e);
      }
    }

    async function triggerScipIngest() {
      const btn = document.getElementById('btn-scip-ingest');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="animate-spin mr-1">⏳</span> Ingesting...';
      }
      try {
        const res = await fetch('/api/scip/auto', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
          alert(`✅ ${data.message}! Type edges populated into FalkorDB.`);
          if (!document.getElementById('tab-content-graph').classList.contains('hidden')) loadGraph();
        } else {
          alert(`ℹ️ SCIP Status: ${data.message}`);
        }
      } catch (e) {
        alert("SCIP ingestion error: " + e);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i data-lucide="play" class="w-3 h-3"></i> Ingest / Run SCIP';
          lucide.createIcons();
        }
      }
    }

    // Blast-Radius Explorer Logic
    async function initBlastTab() {
      await loadBlastAutocomplete();
      const input = document.getElementById('blast-target-input');
      if (!input.value.trim()) {
        input.value = 'SymbolGraphManager';
        executeBlastAnalysis();
      }
    }

    async function loadBlastAutocomplete() {
      const datalist = document.getElementById('blast-suggestions');
      if (!datalist || datalist.children.length > 0) return;
      try {
        const res = await fetch('/api/symbols/autocomplete?limit=150');
        const data = await res.json();
        if (data.status === 'ok' && data.items) {
          datalist.innerHTML = data.items.map(item => `
            <option value="${item.name}">${item.name} (${item.type})</option>
          `).join('');
        }
      } catch (e) {
        console.error("Autocomplete error:", e);
      }
    }

    async function executeBlastAnalysis() {
      const targetInput = document.getElementById('blast-target-input');
      const target = targetInput ? targetInput.value.trim() : '';
      if (!target) return;

      const direction = document.getElementById('blast-direction').value;
      const depth = document.getElementById('blast-depth').value;

      document.getElementById('blast-tree-container').innerHTML = '<div class="text-slate-500 py-12 text-center font-mono">Computing blast radius & dependencies...</div>';

      try {
        const url = `/api/symbols/impact?target=${encodeURIComponent(target)}&direction=${direction}&max_depth=${depth}`;
        const res = await fetch(url);
        const data = await res.json();

        if (data.status !== 'ok') {
          document.getElementById('blast-tree-container').innerHTML = `<div class="p-3 text-rose-400">Analysis failed: ${data.message}</div>`;
          return;
        }

        // 1. Update summary stat badges
        const s = data.summary || {};
        document.getElementById('blast-stat-target').textContent = data.target || target;
        document.getElementById('blast-stat-target').title = data.target || target;
        document.getElementById('blast-stat-type').textContent = s.type || 'symbol';
        document.getElementById('blast-stat-direct').textContent = (s.direct_impact_count || 0).toLocaleString();
        document.getElementById('blast-stat-transitive').textContent = ((s.type_hierarchy_count || 0) + (s.transitive_count || 0)).toLocaleString();
        document.getElementById('blast-stat-total').textContent = (s.total_impacted_locations || 0).toLocaleString();

        const riskEl = document.getElementById('blast-stat-risk');
        if (s.risk_level === 'HIGH') {
          riskEl.className = 'text-xs font-mono px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/30 font-bold';
        } else if (s.risk_level === 'MEDIUM') {
          riskEl.className = 'text-xs font-mono px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-600/60 font-bold';
        } else {
          riskEl.className = 'text-xs font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-bold';
        }
        riskEl.textContent = s.risk_level || 'LOW';

        // 2. Render Graph Canvas
        renderBlastGraph(data.nodes || [], data.edges || []);

        // 3. Render Tree List
        renderBlastTree(data.tree || []);

      } catch (err) {
        document.getElementById('blast-tree-container').innerHTML = `<div class="p-3 text-rose-400">Error: ${err}</div>`;
      }
    }

    let isBlastPhysicsFrozen = true;

    function zoomBlastGraph(factor) {
      if (!blastNetwork) return;
      const scale = blastNetwork.getScale();
      blastNetwork.moveTo({ scale: scale * factor, animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
    }

    function fitBlastGraph() {
      if (!blastNetwork) return;
      blastNetwork.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
    }

    function toggleBlastFreeze() {
      if (!blastNetwork) return;
      isBlastPhysicsFrozen = !isBlastPhysicsFrozen;
      blastNetwork.setOptions({ physics: { enabled: !isBlastPhysicsFrozen } });
      const btn = document.getElementById('btn-blast-freeze');
      if (btn) {
        btn.innerHTML = isBlastPhysicsFrozen 
          ? '<i data-lucide="snowflake" class="w-3.5 h-3.5"></i> Frozen' 
          : '<i data-lucide="flame" class="w-3.5 h-3.5 text-amber-400"></i> Simulating';
        btn.className = isBlastPhysicsFrozen ? 'hud-btn text-emerald-400' : 'hud-btn text-amber-400';
        lucide.createIcons();
      }
    }

    function getEdgeStyle(label, isMention) {
      const lbl = (label || '').toUpperCase().trim();

      // 1. Definition / Origin: Electric Cyan
      if (lbl === 'DEFINED_IN') {
        return {
          color: '#06b6d4',
          highlight: '#22d3ee',
          hover: '#38bdf8',
          width: 1.8,
          dashes: false,
          fontColor: '#38bdf8',
          badgeBg: 'rgba(8, 20, 36, 0.94)'
        };
      }

      // 2. Invocation / References: Vivid Emerald
      if (lbl === 'REFERENCES' || lbl.startsWith('REFERENCES') || lbl === 'CALLS' || lbl.startsWith('CALLS')) {
        return {
          color: '#10b981',
          highlight: '#34d399',
          hover: '#6ee7b7',
          width: 2.0,
          dashes: false,
          fontColor: '#34d399',
          badgeBg: 'rgba(6, 28, 20, 0.94)'
        };
      }

      // 3. Module Imports: Electric Violet / Purple
      if (lbl === 'IMPORTS' || lbl.includes('IMPORTS')) {
        return {
          color: '#8b5cf6',
          highlight: '#a78bfa',
          hover: '#c4b5fd',
          width: 1.8,
          dashes: false,
          fontColor: '#a78bfa',
          badgeBg: 'rgba(22, 14, 46, 0.94)'
        };
      }

      // 4. Implementations / Contracts: Neon Pink / Fuchsia
      if (lbl === 'IMPLEMENTS') {
        return {
          color: '#ec4899',
          highlight: '#f472b6',
          hover: '#fbcfe8',
          width: 2.0,
          dashes: [6, 4],
          fontColor: '#f472b6',
          badgeBg: 'rgba(38, 10, 24, 0.94)'
        };
      }

      // 5. Type Hierarchy: Warm Tangerine / Amber
      if (lbl === 'TYPE_OF' || lbl === 'TYPE' || lbl === 'TAG') {
        return {
          color: '#f97316',
          highlight: '#fb923c',
          hover: '#fed7aa',
          width: 1.8,
          dashes: [3, 4],
          fontColor: '#fb923c',
          badgeBg: 'rgba(36, 16, 6, 0.94)'
        };
      }

      // 6. Dependencies / Blockers: Coral Rose
      if (lbl.includes('DEPENDS') || lbl === 'BLOCKS') {
        return {
          color: '#f43f5e',
          highlight: '#fb7185',
          hover: '#fda4af',
          width: 2.0,
          dashes: false,
          fontColor: '#fb7185',
          badgeBg: 'rgba(36, 8, 14, 0.94)'
        };
      }

      // 7. Causal / Superseded / Historical: Crimson Flame
      if (lbl === 'SUPERSEDES') {
        return {
          color: '#ef4444',
          highlight: '#f87171',
          hover: '#fca5a5',
          width: 2.2,
          dashes: [6, 3],
          fontColor: '#f87171',
          badgeBg: 'rgba(40, 8, 8, 0.94)'
        };
      }

      // 8. Semantic Associations: Sky Blue
      if (lbl === 'RELATES_TO') {
        return {
          color: '#0ea5e9',
          highlight: '#38bdf8',
          hover: '#7dd3fc',
          width: 1.8,
          dashes: false,
          fontColor: '#38bdf8',
          badgeBg: 'rgba(8, 24, 40, 0.94)'
        };
      }

      // 9. Document Links: Luminous Teal
      if (lbl === 'LINKS_TO') {
        return {
          color: '#14b8a6',
          highlight: '#2dd4bf',
          hover: '#5eead4',
          width: 1.8,
          dashes: false,
          fontColor: '#2dd4bf',
          badgeBg: 'rgba(6, 30, 28, 0.94)'
        };
      }

      // 10. Mentions / Context: Muted Steel Slate
      if (isMention || lbl === 'MENTIONS') {
        return {
          color: '#475569',
          highlight: '#94a3b8',
          hover: '#cbd5e1',
          width: 1.2,
          dashes: [4, 4],
          fontColor: '#94a3b8',
          badgeBg: 'rgba(15, 23, 42, 0.94)'
        };
      }

      // Default: Indigo
      return {
        color: '#6366f1',
        highlight: '#818cf8',
        hover: '#c7d2fe',
        width: 1.6,
        dashes: false,
        fontColor: '#818cf8',
        badgeBg: 'rgba(15, 23, 42, 0.94)'
      };
    }

    function formatEdgesNonOverlapping(edgesData) {
      const pairEdgesMap = new Map();
      edgesData.forEach(e => {
        const u = e.from < e.to ? e.from : e.to;
        const v = e.from < e.to ? e.to : e.from;
        const pairKey = `${u}|||${v}`;
        if (!pairEdgesMap.has(pairKey)) {
          pairEdgesMap.set(pairKey, []);
        }
        pairEdgesMap.get(pairKey).push(e);
      });

      const formatted = [];
      pairEdgesMap.forEach((edgeGroup) => {
        const total = edgeGroup.length;
        if (total === 1) {
          const e = edgeGroup[0];
          const style = getEdgeStyle(e.label, e.is_mention);
          formatted.push({
            ...e,
            arrows: e.arrows || { to: { enabled: true, scaleFactor: 0.75 } },
            color: { color: style.color, highlight: style.highlight, hover: style.hover },
            originalColor: { color: style.color, highlight: style.highlight, hover: style.hover },
            width: style.width,
            originalWidth: style.width,
            smooth: { enabled: true, type: 'curvedCW', roundness: 0.16 },
            dashes: style.dashes,
            font: {
              size: 9,
              align: 'middle',
              color: style.fontColor,
              face: 'ui-monospace, SFMono-Regular, monospace',
              background: style.badgeBg
            }
          });
        } else {
          // Multiple edges between the same pair of nodes (or opposite directions)
          // Assign alternating clockwise and counter-clockwise curves with stepped roundness
          // so EVERY single line travels along its own completely separate, non-overlapping arc!
          edgeGroup.forEach((e, idx) => {
            const style = getEdgeStyle(e.label, e.is_mention);
            const step = Math.floor(idx / 2);
            const isCW = (idx % 2 === 0);
            const roundness = 0.18 + (step * 0.16);
            const curveType = isCW ? 'curvedCW' : 'curvedCCW';

            formatted.push({
              ...e,
              arrows: e.arrows || { to: { enabled: true, scaleFactor: 0.75 } },
              color: { color: style.color, highlight: style.highlight, hover: style.hover },
              originalColor: { color: style.color, highlight: style.highlight, hover: style.hover },
              width: style.width,
              originalWidth: style.width,
              smooth: { enabled: true, type: curveType, roundness: roundness },
              dashes: style.dashes,
              font: {
                size: 9,
                align: 'middle',
                color: style.fontColor,
                face: 'ui-monospace, SFMono-Regular, monospace',
                background: style.badgeBg
              }
            });
          });
        }
      });
      return formatted;
    }

    function renderBlastGraph(nodes, edges) {
      const container = document.getElementById('blast-network-graph');
      
      const formattedNodes = nodes.map(n => {
        let icon = '•';
        let bg = '#1e1b4b', border = '#6366f1', hiBg = '#312e81', hiBorder = '#818cf8', fontColor = '#f8fafc';
        let shadowColor = 'rgba(99, 102, 241, 0.35)';

        if (n.level === 0 || n.group === 'target') {
          icon = '🎯';
          bg = '#2e1065'; border = '#818cf8'; hiBg = '#3b0764'; hiBorder = '#c7d2fe'; fontColor = '#ffffff';
          shadowColor = 'rgba(129, 140, 248, 0.45)';
        } else if (n.level === 1) {
          icon = '💥';
          bg = '#450a0a'; border = '#f43f5e'; hiBg = '#7f1d1d'; hiBorder = '#fda4af'; fontColor = '#ffe4e6';
          shadowColor = 'rgba(244, 63, 94, 0.4)';
        } else if (n.level === 2) {
          icon = '⚡';
          bg = '#2a1406'; border = '#f97316'; hiBg = '#3d1d09'; hiBorder = '#fb923c'; fontColor = '#fed7aa';
          shadowColor = 'rgba(249, 115, 22, 0.35)';
        } else {
          icon = '🌐';
          bg = '#082f49'; border = '#38bdf8'; hiBg = '#0c4a6e'; hiBorder = '#bae6fd'; fontColor = '#e0f2fe';
          shadowColor = 'rgba(56, 189, 248, 0.3)';
        }

        const labelText = n.label || n.id;
        const label = (labelText.startsWith('🎯') || labelText.startsWith('💥') || labelText.startsWith('⚡') || labelText.startsWith('🌐'))
          ? labelText
          : `${icon}  ${labelText}`;

        return {
          ...n,
          label: label,
          shape: 'box',
          shapeProperties: { borderRadius: 6 },
          color: { background: bg, border: border, highlight: { background: hiBg, border: hiBorder } },
          font: { 
            color: fontColor, 
            face: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace', 
            size: n.level === 0 ? 12 : 11, 
            bold: { color: fontColor, face: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace', size: n.level === 0 ? 12 : 11 }
          },
          margin: n.level === 0 ? 10 : 8,
          borderWidth: n.level === 0 ? 2.5 : 1.8,
          borderWidthSelected: 3,
          shadow: {
            enabled: true,
            color: shadowColor,
            size: n.level === 0 ? 16 : 12,
            x: 0,
            y: 3
          }
        };
      });

      const formattedEdges = formatEdgesNonOverlapping(edges);

      blastNodesDataSet = new vis.DataSet(formattedNodes);
      blastEdgesDataSet = new vis.DataSet(formattedEdges);

      const options = {
        physics: {
          solver: 'barnesHut',
          barnesHut: {
            gravitationalConstant: -16000,
            centralGravity: 0.08,
            springLength: 170,
            springConstant: 0.035,
            damping: 0.16,
            avoidOverlap: 1.0
          },
          stabilization: { enabled: true, iterations: 160 }
        },
        interaction: { hover: true, tooltipDelay: 150, multiselect: false }
      };

      blastNetwork = new vis.Network(container, { nodes: blastNodesDataSet, edges: blastEdgesDataSet }, options);

      blastNetwork.on("stabilizationIterationsDone", function () {
        blastNetwork.setOptions({ physics: { enabled: false } });
        isBlastPhysicsFrozen = true;
      });
      setTimeout(() => {
        if (blastNetwork) {
          blastNetwork.setOptions({ physics: { enabled: false } });
          isBlastPhysicsFrozen = true;
        }
      }, 1500);

      blastNetwork.on('click', function(params) {
        if (params.nodes.length > 0) {
          const nodeId = params.nodes[0];
          // Neighborhood focus on both nodes and edges
          const connected = blastNetwork.getConnectedNodes(nodeId);
          connected.push(nodeId);
          const connectedSet = new Set(connected);

          const nodeUpdates = blastNodesDataSet.get().map(n => ({
            id: n.id,
            opacity: connectedSet.has(n.id) ? 1.0 : 0.12
          }));
          blastNodesDataSet.update(nodeUpdates);

          const edgeUpdates = blastEdgesDataSet.get().map(e => {
            const isConn = connectedSet.has(e.from) && connectedSet.has(e.to);
            return {
              id: e.id,
              color: isConn 
                ? (e.originalColor || e.color) 
                : { color: 'rgba(30, 41, 59, 0.2)', highlight: 'rgba(30, 41, 59, 0.25)', hover: 'rgba(30, 41, 59, 0.3)' },
              width: isConn ? (e.originalWidth || 1.8) : 1
            };
          });
          blastEdgesDataSet.update(edgeUpdates);

          const row = document.getElementById(`blast-row-${btoa(nodeId).replace(/=/g, '')}`);
          if (row) {
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            row.classList.add('bg-slate-800');
            setTimeout(() => row.classList.remove('bg-slate-800'), 1500);
          }
        } else {
          // Reset blast graph focus
          const nodeUpdates = blastNodesDataSet.get().map(n => ({ id: n.id, opacity: 1.0 }));
          blastNodesDataSet.update(nodeUpdates);
          const edgeUpdates = blastEdgesDataSet.get().map(e => ({
            id: e.id,
            color: e.originalColor || e.color,
            width: e.originalWidth || 1.8
          }));
          blastEdgesDataSet.update(edgeUpdates);
        }
      });
    }

    function renderBlastTree(treeItems) {
      const container = document.getElementById('blast-tree-container');
      document.getElementById('blast-tree-count').textContent = `${treeItems.length} locations`;

      if (!treeItems || treeItems.length === 0) {
        container.innerHTML = '<div class="text-slate-500 py-12 text-center text-xs">No direct callers or dependencies found for this node.</div>';
        return;
      }

      container.innerHTML = treeItems.map(item => {
        const isHigh = item.risk === 'HIGH';
        const isMed = item.risk === 'MEDIUM';
        const badgeColor = isHigh 
          ? 'bg-rose-500/10 text-rose-400 border-rose-500/30' 
          : isMed 
          ? 'bg-amber-950/80 text-amber-300 border-amber-600/60' 
          : 'bg-sky-500/10 text-sky-400 border-sky-500/30';

        const rowId = `blast-row-${btoa(item.source || item.file_path || item.name).replace(/=/g, '')}`;
        const displayPath = (item.file_path || item.source || item.name || '').split('/').slice(-2).join('/');

        return `
          <div id="${rowId}" onclick="focusBlastNode('${item.source || item.file_path || item.name}')" class="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80 hover:border-slate-600 transition cursor-pointer space-y-1.5">
            <div class="flex items-center justify-between">
              <span class="font-bold text-white text-xs truncate max-w-[180px]">${item.name || displayPath}</span>
              <span class="text-[9px] px-1.5 py-0.5 rounded border ${badgeColor} font-bold">${item.risk}</span>
            </div>
            <div class="flex items-center justify-between text-[10px] text-slate-400">
              <span class="text-indigo-400 font-mono">${item.relation}</span>
              ${item.line ? `<span class="text-slate-500 font-mono">Line ${item.line}</span>` : ''}
            </div>
            <div class="text-[10px] text-slate-500 truncate font-mono" title="${item.file_path || item.source || ''}">
              ${item.file_path || item.source || ''}
            </div>
          </div>
        `;
      }).join('');
    }

    function focusBlastNode(nodeId) {
      if (!blastNetwork || !blastNodesDataSet) return;
      if (blastNodesDataSet.get(nodeId)) {
        blastNetwork.focus(nodeId, {
          scale: 1.3,
          animation: { duration: 600, easingFunction: 'easeInOutQuad' }
        });
        blastNetwork.selectNodes([nodeId]);
      }
    }

    async function populateGraphSelector() {
      const select = document.getElementById('select-graph-type');
      if (!select) return;
      try {
        const res = await fetch('/api/graphs');
        const data = await res.json();
        if (data.status === 'ok' && data.graphs && data.graphs.length > 0) {
          const currentVal = select.value || 'kortext';
          const validGraphs = data.graphs.filter(g => g !== 'default_db' && !g.endsWith('_test'));
          select.innerHTML = validGraphs.map(g => {
            let label = `Graph (${g})`;
            if (g === 'kortext') {
              label = `🧠 Episodic & Causal Memory (${g})`;
            } else if (g === 'antigravity_docs') {
              label = '📚 Documentation & Knowledge Graph (antigravity_docs)';
            } else if (g.includes('symbol')) {
              label = `⚡ AST Symbol & Call Graph (${g})`;
            } else {
              label = `🕸️ Knowledge Graph (${g})`;
            }
            return `<option value="${g}">${label}</option>`;
          }).join('');
          if (Array.from(select.options).some(o => o.value === currentVal)) {
            select.value = currentVal;
          }
        }
      } catch (e) {
        console.warn('Could not fetch graphs list:', e);
      }
    }

    async function loadGraph() {
      const statsEl = document.getElementById('graph-stats');
      statsEl.textContent = 'Fetching graph data...';
      const select = document.getElementById('select-graph-type');
      const selectedDb = select ? select.value : 'kortext';
      const EPISODIC_GRAPHS = new Set(['kortext', 'cerebrum']);
      const isSymbols = (selectedDb.includes('symbol') || selectedDb.includes('doc')) || !EPISODIC_GRAPHS.has(selectedDb);
      
      const legendEpisodic = document.getElementById('legend-episodic');
      const legendSymbols = document.getElementById('legend-symbols');
      if (legendEpisodic && legendSymbols) {
        if (isSymbols) {
          legendEpisodic.classList.add('hidden');
          legendSymbols.classList.remove('hidden');
        } else {
          legendEpisodic.classList.remove('hidden');
          legendSymbols.classList.add('hidden');
        }
      }

      const clean = document.getElementById('toggle-hide-mentions').checked;
      try {
        const res = await fetch(`/api/graph?graph_name=${encodeURIComponent(selectedDb)}&clean=${clean}`);
        const data = await res.json();
        if (data.status !== 'ok') {
          statsEl.textContent = 'Error: ' + data.message;
          return;
        }

        allNodes = data.nodes || [];
        allEdges = data.edges || [];
        initRelationshipPalette(allEdges);

        // Anti-Hairball Safeguard for Large Graphs (>250 nodes)
        const largeBanner = document.getElementById('large-graph-banner');
        if (allNodes.length > 250) {
          if (largeBanner) {
            largeBanner.classList.remove('hidden');
            const msg = document.getElementById('large-graph-msg');
            if (msg) msg.textContent = `Large graph (${allNodes.length} nodes, ${allEdges.length} edges). Density leaf-pruning and clustering active to prevent hairballing.`;
          }
          const degSelect = document.getElementById('select-min-degree');
          if (degSelect && degSelect.value === '1') {
            degSelect.value = '2';
            minDegreeFilter = 2;
          }
        } else {
          if (largeBanner) largeBanner.classList.add('hidden');
        }

        applyGraphFilters();
      } catch (e) {
        statsEl.textContent = 'Failed to load graph';
      }
    }

    let activeRelFilters = new Set();
    let relCounts = {};

    function initRelationshipPalette(edges) {
      const container = document.getElementById('rel-filter-list');
      if (!container) return;

      relCounts = {};
      edges.forEach(e => {
        const lbl = (e.label || 'UNKNOWN').toUpperCase().trim();
        relCounts[lbl] = (relCounts[lbl] || 0) + 1;
      });

      const uniqueRels = Object.keys(relCounts).sort();
      activeRelFilters = new Set(uniqueRels);

      if (uniqueRels.length === 0) {
        container.innerHTML = '<div class="text-slate-500 py-3 text-center">No relationships in view</div>';
        return;
      }

      container.innerHTML = uniqueRels.map(rel => {
        const style = getEdgeStyle(rel, false);
        const count = relCounts[rel] || 0;
        const isChecked = activeRelFilters.has(rel) ? 'checked' : '';
        const dashStyle = style.dashes ? 'border-b-2 border-dashed' : 'h-0.5';
        return `
          <label class="flex items-center justify-between p-1.5 rounded hover:bg-slate-800/60 cursor-pointer select-none transition group">
            <div class="flex items-center gap-2">
              <input type="checkbox" id="filter-rel-${rel}" ${isChecked} onchange="toggleRelFilter('${rel}', this.checked)" class="rounded border-slate-700 text-indigo-500 focus:ring-0 w-3 h-3">
              <span class="w-3.5 ${dashStyle}" style="background-color: ${style.dashes ? 'transparent' : style.color}; border-color: ${style.color}; box-shadow: 0 0 6px ${style.color}66;"></span>
              <span class="text-slate-300 group-hover:text-white font-mono text-[10px]">${rel}</span>
            </div>
            <span class="text-[9px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-semibold">${count}</span>
          </label>
        `;
      }).join('');
    }

    function toggleRelFilter(rel, isChecked) {
      if (isChecked) {
        activeRelFilters.add(rel);
      } else {
        activeRelFilters.delete(rel);
      }
      applyGraphFilters();
    }

    function setAllRelFilters(enable) {
      const container = document.getElementById('rel-filter-list');
      if (!container) return;
      const inputs = container.querySelectorAll('input[type="checkbox"]');
      inputs.forEach(input => {
        input.checked = enable;
        const rel = input.id.replace('filter-rel-', '');
        if (enable) activeRelFilters.add(rel);
        else activeRelFilters.delete(rel);
      });
      applyGraphFilters();
    }

    function applyRelPreset(preset) {
      const container = document.getElementById('rel-filter-list');
      if (!container) return;
      const inputs = container.querySelectorAll('input[type="checkbox"]');
      inputs.forEach(input => {
        const rel = input.id.replace('filter-rel-', '').toUpperCase();
        let shouldCheck = false;
        if (preset === 'all') {
          shouldCheck = true;
        } else if (preset === 'calls') {
          shouldCheck = rel.includes('REFERENCES') || rel.includes('CALLS');
        } else if (preset === 'structure') {
          shouldCheck = rel.includes('DEFINED_IN') || rel.includes('IMPORTS') || rel.includes('LINKS');
        } else if (preset === 'types') {
          shouldCheck = rel.includes('IMPLEMENTS') || rel.includes('TYPE');
        }
        input.checked = shouldCheck;
        if (shouldCheck) activeRelFilters.add(rel);
        else activeRelFilters.delete(rel);
      });
      applyGraphFilters();
    }

    function handleToggleClean() {
      const graphType = document.getElementById('select-graph-type') ? document.getElementById('select-graph-type').value : 'episodic';
      if (graphType === 'symbols') {
        loadGraph();
      } else {
        applyGraphFilters();
      }
    }

    // Anti-Hairball State & Handlers
    let minDegreeFilter = 1;
    let currentLayoutMode = 'physics';
    let isNeighborhoodIsolated = false;
    let isolatedFocalNodeId = null;
    let isMacroClustered = false;

    function handleMinDegreeChange(val) {
      minDegreeFilter = parseInt(val, 10) || 1;
      applyGraphFilters();
    }

    function handleLayoutModeChange(val) {
      currentLayoutMode = val;
      applyGraphFilters();
    }

    function isolateNeighborhood(nodeId) {
      if (!nodeId) return;
      isolatedFocalNodeId = nodeId;
      isNeighborhoodIsolated = true;
      const banner = document.getElementById('isolation-banner');
      if (banner) {
        banner.classList.remove('hidden');
        const targetLabel = document.getElementById('isolation-target-label');
        if (targetLabel) targetLabel.textContent = nodeId.split('/').pop() || nodeId;
      }
      applyGraphFilters();
    }

    function exitNeighborhoodIsolation() {
      isNeighborhoodIsolated = false;
      isolatedFocalNodeId = null;
      const banner = document.getElementById('isolation-banner');
      if (banner) banner.classList.add('hidden');
      applyGraphFilters();
    }

    function dismissLargeGraphBanner() {
      const banner = document.getElementById('large-graph-banner');
      if (banner) banner.classList.add('hidden');
    }

    function toggleMacroClustering() {
      if (!network || !nodesDataSet) return;
      isMacroClustered = !isMacroClustered;
      const btn = document.getElementById('btn-toggle-clustering');
      const label = document.getElementById('label-clustering-status');

      if (isMacroClustered) {
        clusterAllModules();
        if (btn) btn.classList.add('bg-indigo-600', 'text-white');
        if (label) label.textContent = 'Macro View (ON)';
      } else {
        unclusterAllModules();
        if (btn) btn.classList.remove('bg-indigo-600', 'text-white');
        if (label) label.textContent = 'Macro View';
      }
    }

    function clusterAllModules() {
      if (!network || !nodesDataSet) return;
      const allN = nodesDataSet.get();
      const clusterGroups = new Map();
      allN.forEach(n => {
        const cid = n.cluster_id || 'general';
        const cname = n.cluster_name || cid;
        if (!clusterGroups.has(cid)) {
          clusterGroups.set(cid, { id: cid, name: cname, count: 0 });
        }
        clusterGroups.get(cid).count++;
      });

      clusterGroups.forEach((info, cid) => {
        if (info.count >= 2) {
          network.cluster({
            joinCondition: function (nodeOptions) {
              return nodeOptions.cluster_id === cid;
            },
            processProperties: function (clusterOptions, childNodes, childEdges) {
              clusterOptions.label = `📦 ${info.name}\n[${childNodes.length} components]`;
              clusterOptions.title = `<b>Subsystem / Module: ${info.name}</b><br/>Contains ${childNodes.length} nodes.<br/><i>Double-click to expand</i>`;
              clusterOptions.shape = 'box';
              clusterOptions.size = 24;
              clusterOptions.margin = 12;
              clusterOptions.color = {
                background: '#1e1b4b',
                border: '#818cf8',
                highlight: { background: '#312e81', border: '#c7d2fe' }
              };
              clusterOptions.font = {
                color: '#e0e7ff',
                face: 'ui-monospace, SFMono-Regular, monospace',
                size: 11,
                bold: true,
                multi: true
              };
              clusterOptions.borderWidth = 2.5;
              clusterOptions.shadow = { enabled: true, color: 'rgba(129, 140, 248, 0.45)', size: 16 };
              return clusterOptions;
            },
            clusterNodeProperties: {
              id: 'cluster:' + cid,
              borderWidth: 2.5,
              allowSingleNodeCluster: false
            }
          });
        }
      });
      isMacroClustered = true;
      const btn = document.getElementById('btn-toggle-clustering');
      const label = document.getElementById('label-clustering-status');
      if (btn) btn.classList.add('bg-indigo-600', 'text-white');
      if (label) label.textContent = 'Macro View (ON)';
    }

    function unclusterAllModules() {
      if (!network) return;
      const nodeIds = network.body.nodeIndices;
      for (let i = 0; i < nodeIds.length; i++) {
        if (network.isCluster(nodeIds[i])) {
          network.openCluster(nodeIds[i]);
        }
      }
      isMacroClustered = false;
      const btn = document.getElementById('btn-toggle-clustering');
      const label = document.getElementById('label-clustering-status');
      if (btn) btn.classList.remove('bg-indigo-600', 'text-white');
      if (label) label.textContent = 'Macro View';
    }

    function openClusterDrawer(clusterId) {
      const inspectorContent = document.getElementById('inspector-content');
      const inspectorBadge = document.getElementById('inspector-badge');
      if (inspectorBadge) {
        inspectorBadge.textContent = 'Macro Subsystem';
        inspectorBadge.className = 'text-[9px] font-mono px-2 py-0.5 rounded uppercase font-semibold border bg-indigo-950/90 text-indigo-300 border-indigo-500/50';
        inspectorBadge.classList.remove('hidden');
      }
      const nodesInCluster = network.getNodesInCluster(clusterId);
      const cleanId = clusterId.replace('cluster:', '');
      if (inspectorContent) {
        inspectorContent.innerHTML = `
          <div class="space-y-3">
            <div class="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1.5">
              <div class="font-bold text-white text-xs truncate">
                📦 Subsystem / Module: ${cleanId}
              </div>
              <div class="text-[10px] font-mono text-slate-400">
                Encapsulates ${nodesInCluster.length} components.
              </div>
              <div class="text-[10px] font-mono text-slate-500 pt-1 border-t border-slate-800">
                Double-click on canvas or click below to drill into this cluster.
              </div>
            </div>
            <button onclick="network.openCluster('${clusterId}')" class="w-full py-1.5 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-mono text-xs flex items-center justify-center gap-1.5 transition shadow">
              <i data-lucide="maximize-2" class="w-3.5 h-3.5"></i> Expand This Subsystem
            </button>
          </div>
        `;
        if (window.lucide) lucide.createIcons();
      }
    }

    function applyGraphFilters() {
      const hideMentions = document.getElementById('toggle-hide-mentions') ? document.getElementById('toggle-hide-mentions').checked : false;
      
      let filteredEdges = allEdges;
      if (hideMentions) {
        filteredEdges = filteredEdges.filter(e => !e.is_mention);
      }

      if (activeRelFilters && activeRelFilters.size >= 0) {
        filteredEdges = filteredEdges.filter(e => {
          const lbl = (e.label || '').toUpperCase().trim();
          return activeRelFilters.has(lbl);
        });
      }

      let filteredNodes = allNodes;

      // 1. Ego-Network Isolation Mode (Solo Neighborhood Focus)
      if (isNeighborhoodIsolated && isolatedFocalNodeId) {
        const hopRadius = document.getElementById('select-hop-radius') ? document.getElementById('select-hop-radius').value : '1';
        const neighborList = getNeighborhood(isolatedFocalNodeId, hopRadius);
        const neighborSet = new Set(neighborList);
        neighborSet.add(isolatedFocalNodeId);

        filteredNodes = filteredNodes.filter(n => neighborSet.has(n.id));
        const visNodeIds = new Set(filteredNodes.map(n => n.id));
        filteredEdges = filteredEdges.filter(e => visNodeIds.has(e.from) && visNodeIds.has(e.to));
        const hopCountEl = document.getElementById('isolation-hop-count');
        if (hopCountEl) hopCountEl.textContent = Math.max(0, filteredNodes.length - 1);
      } else {
        // 2. Degree Centrality Filter (Density / Leaf Pruning)
        if (minDegreeFilter > 1) {
          filteredNodes = filteredNodes.filter(n => (n.degree || 0) >= minDegreeFilter);
          const visNodeIds = new Set(filteredNodes.map(n => n.id));
          filteredEdges = filteredEdges.filter(e => visNodeIds.has(e.from) && visNodeIds.has(e.to));
        }

        // 3. Rel Type Connection Filter
        if (hideMentions || (activeRelFilters && activeRelFilters.size < Object.keys(relCounts).length)) {
          const connectedNodeIds = new Set();
          filteredEdges.forEach(e => {
            connectedNodeIds.add(e.from);
            connectedNodeIds.add(e.to);
          });
          filteredNodes = filteredNodes.filter(n => connectedNodeIds.has(n.id) || n.group === 'file');
        }
      }

      const statsEl = document.getElementById('graph-stats');
      if (statsEl) {
        statsEl.textContent = `${filteredNodes.length} Visible Nodes • ${filteredEdges.length} Visible Relationships`;
      }
      renderGraph(filteredNodes, filteredEdges);
      if (isMacroClustered) {
        setTimeout(() => clusterAllModules(), 200);
      }
    }

    function zoomGraph(factor) {
      if (!network) return;
      const scale = network.getScale();
      network.moveTo({ scale: scale * factor, animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
    }

    function fitGraph() {
      if (!network) return;
      network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
    }

    function renderGraph(nodesData, edgesData) {
      const container = document.getElementById('network-graph');
      
      const formattedNodes = nodesData.map(n => {
        const isEpisodic = n.group === 'episodic';
        const isFile = n.group === 'file';
        const isSymbol = n.group === 'symbol';

        let icon = '●';
        let bg = '#0f172a', border = '#38bdf8', hiBg = '#1e293b', hiBorder = '#7dd3fc', fontColor = '#f8fafc';
        let shape = 'box';
        let size = 16;
        let shadowColor = 'rgba(56, 189, 248, 0.25)';

        if (isEpisodic) {
          icon = '💡';
          bg = '#2a1406'; border = '#f97316'; hiBg = '#3d1d09'; hiBorder = '#fb923c'; fontColor = '#fed7aa';
          shape = 'box'; size = 20; shadowColor = 'rgba(249, 115, 22, 0.35)';
        } else if (n.group === 'document') {
          icon = '📄';
          bg = '#083344'; border = '#06b6d4'; hiBg = '#164e63'; hiBorder = '#22d3ee'; fontColor = '#cffafe';
          shape = 'box'; size = 18; shadowColor = 'rgba(6, 182, 212, 0.35)';
        } else if (n.group === 'tag') {
          icon = '🏷️';
          bg = '#1e293b'; border = '#38bdf8'; hiBg = '#334155'; hiBorder = '#7dd3fc'; fontColor = '#e2e8f0';
          shape = 'box'; size = 14; shadowColor = 'rgba(56, 189, 248, 0.25)';
        } else if (n.group === 'concept') {
          icon = '💎';
          bg = '#500724'; border = '#ec4899'; hiBg = '#700936'; hiBorder = '#f472b6'; fontColor = '#fce7f3';
          shape = 'box'; size = 16; shadowColor = 'rgba(236, 72, 153, 0.35)';
        } else if (isFile) {
          icon = '📁';
          bg = '#1e1b4b'; border = '#6366f1'; hiBg = '#312e81'; hiBorder = '#818cf8'; fontColor = '#e0e7ff';
          shape = 'box'; size = 18; shadowColor = 'rgba(99, 102, 241, 0.35)';
        } else if (isSymbol) {
          icon = '⚡';
          bg = '#022c22'; border = '#10b981'; hiBg = '#064e3b'; hiBorder = '#34d399'; fontColor = '#a7f3d0';
          shape = 'box'; size = 14; shadowColor = 'rgba(16, 185, 129, 0.35)';
        }

        const labelText = n.label || n.id;
        const label = (labelText.startsWith('📁') || labelText.startsWith('📄') || labelText.startsWith('⚡') || labelText.startsWith('💡') || labelText.startsWith('🏷️') || labelText.startsWith('💎'))
          ? labelText
          : `${icon}  ${labelText}`;

        return {
          id: n.id,
          label: label,
          full_name: n.full_name || n.id,
          group: n.group,
          cluster_id: n.cluster_id || 'general',
          cluster_name: n.cluster_name || 'General',
          degree: n.degree || 0,
          color: { background: bg, border: border, highlight: { background: hiBg, border: hiBorder } },
          font: { 
            color: fontColor, 
            face: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace', 
            size: (isEpisodic || isFile) ? 11 : 12,
            bold: { color: fontColor, face: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace', size: (isEpisodic || isFile) ? 11 : 12 }
          },
          shape: shape,
          shapeProperties: { borderRadius: 6 },
          size: size,
          margin: 8,
          borderWidth: 1.5,
          borderWidthSelected: 2.5,
          shadow: {
            enabled: true,
            color: shadowColor,
            size: 12,
            x: 0,
            y: 3
          }
        };
      });

      const formattedEdges = formatEdgesNonOverlapping(edgesData);

      nodesDataSet = new vis.DataSet(formattedNodes);
      edgesDataSet = new vis.DataSet(formattedEdges);

      let options;
      if (currentLayoutMode === 'hierarchical-lr') {
        options = {
          layout: {
            hierarchical: {
              enabled: true,
              direction: 'LR',
              sortMethod: 'directed',
              levelSeparation: 220,
              nodeSpacing: 160,
              treeSpacing: 180,
              blockShifting: true,
              edgeMinimization: true,
              parentCentralization: true
            }
          },
          physics: {
            solver: 'hierarchicalRepulsion',
            hierarchicalRepulsion: {
              nodeDistance: 160,
              centralGravity: 0.0,
              springLength: 160,
              springConstant: 0.01,
              damping: 0.15
            },
            stabilization: { enabled: true, iterations: 120 }
          },
          interaction: { hover: true, tooltipDelay: 150, multiselect: false }
        };
      } else if (currentLayoutMode === 'hierarchical-ud') {
        options = {
          layout: {
            hierarchical: {
              enabled: true,
              direction: 'UD',
              sortMethod: 'directed',
              levelSeparation: 180,
              nodeSpacing: 180,
              treeSpacing: 200,
              blockShifting: true,
              edgeMinimization: true,
              parentCentralization: true
            }
          },
          physics: {
            solver: 'hierarchicalRepulsion',
            hierarchicalRepulsion: {
              nodeDistance: 160,
              centralGravity: 0.0,
              springLength: 160,
              springConstant: 0.01,
              damping: 0.15
            },
            stabilization: { enabled: true, iterations: 120 }
          },
          interaction: { hover: true, tooltipDelay: 150, multiselect: false }
        };
      } else {
        options = {
          physics: {
            solver: 'barnesHut',
            barnesHut: {
              gravitationalConstant: -18000,
              centralGravity: 0.08,
              springLength: 180,
              springConstant: 0.035,
              damping: 0.16,
              avoidOverlap: 1.0
            },
            stabilization: { enabled: true, iterations: 160 }
          },
          interaction: { hover: true, tooltipDelay: 150, multiselect: false }
        };
      }

      network = new vis.Network(container, { nodes: nodesDataSet, edges: edgesDataSet }, options);

      // Hard-Freeze Protocol: Lock coordinates after initial stabilization (Section 36)
      network.on("stabilizationIterationsDone", function () {
        network.setOptions({ physics: { enabled: false } });
        setFreezeState(true);
      });

      // Failsafe timer (1500ms)
      setTimeout(() => {
        if (network) {
          network.setOptions({ physics: { enabled: false } });
          setFreezeState(true);
        }
      }, 1500);
      
      network.on('click', function(params) {
        if (params.nodes.length > 0) {
          const nodeId = params.nodes[0];
          if (network.isCluster(nodeId)) {
            openClusterDrawer(nodeId);
            return;
          }
          const node = nodesDataSet.get(nodeId);
          focusNode(nodeId);
          openDrawer(node);
        } else {
          resetGraphFocus();
          closeDrawer();
        }
      });

      // Double-click to expand cluster smoothly in place
      network.on('doubleClick', function(params) {
        if (params.nodes.length === 1) {
          const clickedId = params.nodes[0];
          if (network.isCluster(clickedId)) {
            network.openCluster(clickedId);
          }
        }
      });
    }

    let currentFocusedNodeId = null;

    function getNeighborhood(startNodeId, radius) {
      if (radius === 'all') {
        const visited = new Set([startNodeId]);
        const queue = [startNodeId];
        while (queue.length > 0) {
          const curr = queue.shift();
          const neighbors = network.getConnectedNodes(curr);
          for (const n of neighbors) {
            if (!visited.has(n)) {
              visited.add(n);
              queue.push(n);
            }
          }
        }
        return Array.from(visited);
      }

      const r = parseInt(radius, 10) || 1;
      let currentLevel = new Set([startNodeId]);
      const visited = new Set([startNodeId]);

      for (let hop = 0; hop < r; hop++) {
        const nextLevel = new Set();
        for (const nid of currentLevel) {
          const neighbors = network.getConnectedNodes(nid);
          for (const neighbor of neighbors) {
            if (!visited.has(neighbor)) {
              visited.add(neighbor);
              nextLevel.add(neighbor);
            }
          }
        }
        currentLevel = nextLevel;
      }
      return Array.from(visited);
    }

    function updateFocusRadius() {
      if (currentFocusedNodeId) {
        focusNode(currentFocusedNodeId);
      }
    }

    function focusNode(nodeId) {
      currentFocusedNodeId = nodeId;
      const radius = document.getElementById('select-hop-radius') ? document.getElementById('select-hop-radius').value : '1';
      const isolated = document.getElementById('toggle-isolated-focus') ? document.getElementById('toggle-isolated-focus').checked : false;

      const connected = getNeighborhood(nodeId, radius);

      if (isolated) {
        // Physical slicing: only show connected nodes and their connecting edges
        const connectedSet = new Set(connected);
        const filteredNodes = allNodes.filter(n => connectedSet.has(n.id));
        const filteredEdges = allEdges.filter(e => connectedSet.has(e.from) && connectedSet.has(e.to));
        renderGraph(filteredNodes, filteredEdges);
      } else {
        // Visual dimming of both nodes and edges
        const connectedSet = new Set(connected);
        const allNodeUpdates = nodesDataSet.get().map(n => ({
          id: n.id,
          opacity: connectedSet.has(n.id) ? 1.0 : 0.12,
          hidden: false
        }));
        nodesDataSet.update(allNodeUpdates);

        const allEdgeUpdates = edgesDataSet.get().map(e => {
          const isConn = connectedSet.has(e.from) && connectedSet.has(e.to);
          return {
            id: e.id,
            color: isConn 
              ? (e.originalColor || e.color) 
              : { color: 'rgba(30, 41, 59, 0.2)', highlight: 'rgba(30, 41, 59, 0.25)', hover: 'rgba(30, 41, 59, 0.3)' },
            width: isConn ? (e.originalWidth || 1.8) : 1
          };
        });
        edgesDataSet.update(allEdgeUpdates);
      }
    }

    function resetGraphFocus() {
      currentFocusedNodeId = null;
      document.getElementById('graph-search').value = '';
      if (nodesDataSet && edgesDataSet) {
        const nodeUpdates = nodesDataSet.get().map(n => ({ id: n.id, opacity: 1.0 }));
        nodesDataSet.update(nodeUpdates);
        const edgeUpdates = edgesDataSet.get().map(e => ({
          id: e.id,
          color: e.originalColor || e.color,
          width: e.originalWidth || 1.8
        }));
        edgesDataSet.update(edgeUpdates);
      }
      applyGraphFilters();
    }

    function filterGraphBySearch() {
      const q = document.getElementById('graph-search').value.toLowerCase().trim();
      if (!q || !nodesDataSet) {
        resetGraphFocus();
        return;
      }

      const match = nodesDataSet.get().find(n => (n.full_name || n.id).toLowerCase().includes(q));
      if (match) {
        network.focus(match.id, { scale: 1.2, animation: true });
        focusNode(match.id);
        openDrawer(match);
      }
    }

    function openDrawer(node) {
      const inspectorContent = document.getElementById('inspector-content');
      const inspectorBadge = document.getElementById('inspector-badge');
      if (!inspectorContent || !node) return;

      const isEpisodic = node.group === 'episodic';
      const isFile = node.group === 'file';
      const isSymbol = node.group === 'symbol';
      const isDocument = node.group === 'document';
      const isTag = node.group === 'tag';
      const isConcept = node.group === 'concept';

      let tagText = 'Entity';
      let tagClass = 'bg-cyan-950/80 text-cyan-300 border-cyan-600/50';

      if (isEpisodic) {
        tagText = 'Episodic Decision';
        tagClass = 'bg-amber-950/90 text-amber-300 border-amber-600/60 font-bold';
      } else if (isDocument) {
        tagText = 'Markdown Note';
        tagClass = 'bg-cyan-950/80 text-cyan-300 border-cyan-600/50';
      } else if (isTag) {
        tagText = 'Topic Tag';
        tagClass = 'bg-amber-950/90 text-amber-300 border-amber-600/60 font-bold';
      } else if (isConcept) {
        tagText = 'Vault Concept';
        tagClass = 'bg-pink-950/80 text-pink-300 border-pink-600/50';
      } else if (isFile) {
        tagText = 'Source File';
        tagClass = 'bg-indigo-950/80 text-indigo-300 border-indigo-600/50';
      } else if (isSymbol) {
        tagText = 'Code Symbol';
        tagClass = 'bg-emerald-950/80 text-emerald-300 border-emerald-600/50';
      }

      if (inspectorBadge) {
        inspectorBadge.textContent = tagText;
        inspectorBadge.className = `text-[9px] font-mono px-2 py-0.5 rounded uppercase font-semibold border ${tagClass}`;
        inspectorBadge.classList.remove('hidden');
      }

      const connectedEdges = edgesDataSet ? edgesDataSet.get({
        filter: e => e.from === node.id || e.to === node.id
      }) : [];

      const outgoing = connectedEdges.filter(e => e.from === node.id);
      const incoming = connectedEdges.filter(e => e.to === node.id);

      const renderRelItem = (e, isOut) => {
        const otherId = isOut ? e.to : e.from;
        const arrow = isOut ? '→' : '←';
        const style = getEdgeStyle(e.label, false);
        const displayName = otherId.split('/').slice(-2).join('/');
        return `
          <div class="flex items-center justify-between p-1.5 rounded bg-slate-950/70 border border-slate-800 hover:border-slate-700 transition gap-1.5">
            <div class="flex items-center gap-1.5 overflow-hidden">
              <span class="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded shrink-0" style="color: ${style.fontColor}; background: ${style.badgeBg}; border: 1px solid ${style.color}55;">
                ${arrow} ${e.label}
              </span>
              <span class="text-slate-300 font-mono text-[11px] truncate max-w-[130px]" title="${otherId}">${displayName}</span>
            </div>
            <button onclick="flyToNode('${otherId}')" class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-indigo-400 hover:text-indigo-300 border border-slate-700 shrink-0 transition" title="Focus ${otherId}">
              Focus
            </button>
          </div>
        `;
      };

      const select = document.getElementById('select-graph-type');
      const selectedDb = select ? select.value : 'kortext';
      const dbName = selectedDb.includes('symbol') ? 'kortext_symbols' : selectedDb;

      inspectorContent.innerHTML = `
        <div class="space-y-2.5">
          <div class="p-2 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
            <div class="font-bold text-white text-xs truncate" title="${node.full_name || node.id}">
              ${node.label || node.id}
            </div>
            <div class="text-[10px] font-mono text-slate-400 truncate" title="${node.id}">
              ID: ${node.id}
            </div>
            <div class="flex items-center justify-between text-[10px] font-mono text-slate-500 pt-1 border-t border-slate-800/80">
              <span>Subsystem:</span>
              <span class="text-indigo-400 font-semibold truncate max-w-[140px]">${node.cluster_name || 'Core'}</span>
            </div>
            <div class="flex items-center justify-between text-[10px] font-mono text-slate-500">
              <span>Degree:</span>
              <span class="text-emerald-400 font-semibold">${node.degree !== undefined ? node.degree : (outgoing.length + incoming.length)} connections</span>
            </div>
            <div class="flex items-center justify-between text-[10px] font-mono text-slate-500">
              <span>Database:</span>
              <span class="text-indigo-400 font-semibold">${dbName}</span>
            </div>
            <button onclick="isolateNeighborhood('${node.id}')" class="w-full mt-1.5 py-1.5 px-2.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/60 border border-indigo-500/50 text-indigo-300 hover:text-white font-mono text-[11px] flex items-center justify-center gap-1.5 transition shadow">
              <i data-lucide="crosshair" class="w-3.5 h-3.5 text-cyan-400"></i> Isolate Neighborhood (Ego-View)
            </button>
          </div>

          <div class="space-y-1.5">
            <div class="flex items-center justify-between text-[11px] font-mono">
              <span class="text-slate-400 font-semibold">Outgoing (${outgoing.length}):</span>
              <span class="text-[10px] text-slate-500">Dependencies</span>
            </div>
            <div class="space-y-1 max-h-36 overflow-y-auto pr-0.5">
              ${outgoing.length > 0 ? outgoing.map(e => renderRelItem(e, true)).join('') : '<span class="text-[10px] text-slate-600 block py-1">No outgoing connections</span>'}
            </div>
          </div>

          <div class="space-y-1.5 pt-1.5 border-t border-slate-800">
            <div class="flex items-center justify-between text-[11px] font-mono">
              <span class="text-slate-400 font-semibold">Incoming (${incoming.length}):</span>
              <span class="text-[10px] text-slate-500">Callers & Dependents</span>
            </div>
            <div class="space-y-1 max-h-36 overflow-y-auto pr-0.5">
              ${incoming.length > 0 ? incoming.map(e => renderRelItem(e, false)).join('') : '<span class="text-[10px] text-slate-600 block py-1">No incoming connections</span>'}
            </div>
          </div>
        </div>
      `;
    }

    function closeDrawer() {
      const inspectorContent = document.getElementById('inspector-content');
      const inspectorBadge = document.getElementById('inspector-badge');
      if (inspectorBadge) inspectorBadge.classList.add('hidden');
      if (inspectorContent) {
        inspectorContent.innerHTML = `
          <div class="text-slate-500 text-xs py-4 text-center font-mono">
            Click any node in the canvas to inspect its exact incoming and outgoing relationships.
          </div>
        `;
      }
    }

    function flyToNode(nodeId) {
      if (!network || !nodesDataSet) return;
      const targetNode = nodesDataSet.get(nodeId);
      if (targetNode) {
        network.focus(nodeId, { scale: 1.15, animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
        focusNode(nodeId);
        openDrawer(targetNode);
      }
    }

    async function loadJournal() {
      try {
        const res = await fetch('/api/journal');
        const data = await res.json();
        allJournalEntries = data.entries || [];
        renderJournal(allJournalEntries);
      } catch (e) {
        document.getElementById('journal-timeline').innerHTML = '<div class="text-rose-400">Failed to load journal.</div>';
      }
    }

    function renderJournal(entries) {
      const container = document.getElementById('journal-timeline');
      if (entries.length === 0) {
        container.innerHTML = '<div class="text-slate-500 py-8 text-center">No journal entries found.</div>';
        return;
      }
      container.innerHTML = entries.map(e => `
        <div class="bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/60 pb-3">
            <div class="flex items-center gap-3">
              <span class="text-xs font-mono bg-indigo-500/10 text-indigo-400 px-2 py-0.5 rounded border border-indigo-500/30">${e.date}</span>
              <h3 class="font-semibold text-white text-base">${e.title}</h3>
            </div>
            ${e.project ? `<span class="text-xs font-mono bg-slate-800 text-slate-300 px-2 py-0.5 rounded">Project: ${e.project}</span>` : ''}
          </div>
          <p class="text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">${e.body}</p>
          ${e.tags && e.tags.length > 0 ? `
            <div class="flex flex-wrap gap-1.5 pt-2">
              ${e.tags.map(t => `<span class="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full">#${t}</span>`).join('')}
            </div>
          ` : ''}
        </div>
      `).join('');
    }

    function filterJournal() {
      const q = document.getElementById('journal-search').value.toLowerCase();
      const filtered = allJournalEntries.filter(e => 
        e.title.toLowerCase().includes(q) || 
        e.body.toLowerCase().includes(q) || 
        (e.tags && e.tags.some(t => t.toLowerCase().includes(q)))
      );
      renderJournal(filtered);
    }

    async function loadCollections() {
      const container = document.getElementById('collections-grid');
      container.innerHTML = '<div class="text-slate-500 py-4 col-span-3 text-center">Fetching Qdrant collections...</div>';
      try {
        const res = await fetch('/api/collections');
        const data = await res.json();
        if (data.status !== 'ok' || !data.collections) {
          container.innerHTML = `<div class="text-rose-400 col-span-3">Failed to load collections: ${data.message || 'Error'}</div>`;
          return;
        }

        if (data.collections.length === 0) {
          container.innerHTML = '<div class="text-slate-500 py-4 col-span-3 text-center">No collections found in Qdrant.</div>';
          return;
        }

        container.innerHTML = data.collections.map(c => `
          <div class="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
            <div class="flex items-center justify-between border-b border-slate-800/80 pb-2">
              <span class="font-bold text-white text-sm font-mono">${c.name}</span>
              <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 uppercase">${c.status}</span>
            </div>
            <div class="grid grid-cols-2 gap-2 text-xs font-mono">
              <div>
                <span class="text-slate-500 block text-[10px]">Points / Chunks:</span>
                <span class="text-slate-200 font-bold">${c.points_count.toLocaleString()}</span>
              </div>
              <div>
                <span class="text-slate-500 block text-[10px]">Vectors:</span>
                <span class="text-slate-200 font-bold">${c.vectors_count.toLocaleString()}</span>
              </div>
            </div>
            <div class="pt-2 border-t border-slate-800/60 flex justify-between items-center text-xs">
              <span class="text-[10px] text-slate-500">Dual-Vector: 4096-dim + BM25</span>
              <span class="text-emerald-400 font-mono text-[11px]">Qdrant (WAL + Mmap)</span>
            </div>
          </div>
        `).join('');
      } catch (e) {
        container.innerHTML = `<div class="text-rose-400 col-span-3">Error fetching collections: ${e}</div>`;
      }
    }

    async function createNewCollection() {
      const input = document.getElementById('new-collection-name');
      const name = input.value.trim();
      if (!name) {
        alert("Please enter a collection name.");
        return;
      }

      try {
        const res = await fetch('/api/collections', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          input.value = '';
          alert(`✅ Collection '${name}' created successfully in Qdrant!`);
          loadCollections();
        } else {
          alert(`Failed to create collection: ${data.error || JSON.stringify(data)}`);
        }
      } catch (e) {
        alert(`Error: ${e}`);
      }
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    async function populateRetrievalCollections() {
      const select = document.getElementById('retrieval-collection');
      if (!select) return;
      try {
        const res = await fetch('/api/collections');
        const data = await res.json();
        const cols = (data.collections || []).map(c => typeof c === 'string' ? c : c.name);
        const currentVal = select.value || 'all';
        let opts = `<option value="all">🌐 All Collections (Federated)</option>`;
        for (const c of cols) {
          const isDocs = c.toLowerCase().includes('doc');
          const icon = isDocs ? '📚' : '📦';
          opts += `<option value="${c}">${icon} ${c}</option>`;
        }
        select.innerHTML = opts;
        if (Array.from(select.options).some(o => o.value === currentVal)) {
          select.value = currentVal;
        }
      } catch (e) {
        console.warn('Could not populate retrieval collections:', e);
      }
    }

    async function executeRetrieval() {
      const qInput = document.getElementById('retrieval-query');
      const q = qInput ? qInput.value.trim() : '';
      const colSelect = document.getElementById('retrieval-collection');
      const col = colSelect ? colSelect.value.trim() : 'all';
      const budgetSelect = document.getElementById('retrieval-budget');
      const budget = budgetSelect ? parseInt(budgetSelect.value, 10) || 1500 : 1500;
      if (!q) return;

      const t0 = document.getElementById('tier0-content');
      const t1 = document.getElementById('tier1-content');
      const t2 = document.getElementById('tier2-content');

      if (t0) t0.innerHTML = '<span class="text-sky-400">Seeking AST symbols...</span>';
      if (t1) t1.innerHTML = '<span class="text-emerald-400">Reranking codebase chunks with RRF...</span>';
      if (t2) t2.innerHTML = '<span class="text-purple-400">Querying episodic history & Weibull retention...</span>';

      try {
        const payload = {
          query: q,
          collection: col === 'all' ? null : col,
          token_budget: budget
        };

        const res = await fetch('/api/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();

        // Update Token Budget Metrics
        const tokenBadge = document.getElementById('retrieval-tokens-badge');
        const tokenUsed = document.getElementById('retrieval-tokens-used');
        const tokenMax = document.getElementById('retrieval-tokens-max');
        if (tokenBadge) tokenBadge.classList.remove('hidden');
        if (tokenUsed) tokenUsed.textContent = (data.total_estimated_tokens || 0).toLocaleString();
        if (tokenMax) tokenMax.textContent = budget.toLocaleString();

        // Tier 0: AST Symbols
        const symbols = data.symbolic_context || [];
        const t0Count = document.getElementById('tier0-count');
        if (t0Count) t0Count.textContent = `${symbols.length} symbol${symbols.length === 1 ? '' : 's'}`;
        if (t0) {
          if (symbols.length > 0) {
            t0.innerHTML = symbols.map(s => {
              if (typeof s === 'string') {
                return `<div class="p-2.5 bg-slate-950/70 rounded border border-slate-800/80 text-xs">${escapeHtml(s)}</div>`;
              }
              const symName = s.symbol || s.name || 'Symbol';
              const symKind = s.kind || s.type || 'identifier';
              const symFile = s.file || s.file_path || '';
              const symLines = s.lines ? `:${s.lines[0]}-${s.lines[1]}` : (s.line ? `:${s.line}` : '');
              const symSig = s.signature || '';
              const symDoc = s.docstring || '';
              const symCode = s.code || '';

              return `
                <div class="p-2.5 bg-slate-950/70 rounded border border-slate-800/80 space-y-1.5 hover:border-sky-500/40 transition">
                  <div class="flex items-center justify-between gap-1">
                    <span class="text-xs text-sky-400 font-bold font-mono">${escapeHtml(symName)}</span>
                    <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-950/80 text-sky-300 border border-sky-800/60 uppercase">${escapeHtml(symKind)}</span>
                  </div>
                  ${symFile ? `
                    <div class="text-[10px] text-slate-400 font-mono truncate" title="${escapeHtml(symFile)}">
                      ${escapeHtml(symFile.split('/').slice(-2).join('/'))}${symLines}
                    </div>
                  ` : ''}
                  ${symSig ? `<pre class="text-[10px] font-mono text-slate-300 bg-slate-900/60 p-1.5 rounded overflow-x-auto">${escapeHtml(symSig)}</pre>` : ''}
                  ${symDoc ? `<p class="text-[10px] text-slate-400 italic">${escapeHtml(symDoc)}</p>` : ''}
                  ${symCode && !symSig ? `<pre class="text-[10px] font-mono text-slate-300 bg-slate-900/60 p-1.5 rounded max-h-32 overflow-y-auto">${escapeHtml(symCode)}</pre>` : ''}
                </div>
              `;
            }).join('');
          } else {
            t0.innerHTML = '<span class="text-slate-500">No exact AST symbols matched.</span>';
          }
        }

        // Tier 1: Reranked Code with RRF signals
        const chunks = data.code_chunks || [];
        const t1Count = document.getElementById('tier1-count');
        if (t1Count) t1Count.textContent = `${chunks.length} chunk${chunks.length === 1 ? '' : 's'}`;
        if (t1) {
          if (chunks.length > 0) {
            t1.innerHTML = chunks.map((c, idx) => {
              const raw = typeof c === 'string' ? c : (c.text || c.snippet || JSON.stringify(c));
              const fileMatch = raw.match(/^\[(.*?)\]\s*/);
              const sourceHeader = fileMatch ? fileMatch[1] : null;
              const snippetBody = fileMatch ? raw.slice(fileMatch[0].length) : raw;

              return `
                <div class="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-2 hover:border-emerald-500/40 transition">
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/60">#${idx + 1} RRF Rank</span>
                    ${sourceHeader ? `<span class="text-[10px] font-mono text-slate-400 truncate max-w-[180px]" title="${escapeHtml(sourceHeader)}">${escapeHtml(sourceHeader.split('/').slice(-2).join('/'))}</span>` : ''}
                  </div>
                  <pre class="text-[11px] font-mono whitespace-pre-wrap text-slate-200 leading-relaxed max-h-52 overflow-y-auto bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">${escapeHtml(snippetBody)}</pre>
                </div>
              `;
            }).join('');
          } else {
            t1.innerHTML = '<span class="text-slate-500">No code chunks retrieved.</span>';
          }
        }

        // Tier 2: Episodic Memory with Weibull retention
        const facts = data.episodic_history || [];
        const t2Count = document.getElementById('tier2-count');
        if (t2Count) t2Count.textContent = `${facts.length} fact${facts.length === 1 ? '' : 's'}`;
        if (t2) {
          if (facts.length > 0) {
            t2.innerHTML = facts.map(f => {
              const factText = typeof f === 'string' ? f : (f.fact || f.content || JSON.stringify(f));
              return `
                <div class="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-1.5 hover:border-purple-500/40 transition">
                  <div class="flex items-center justify-between">
                    <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-800/60">Weibull Active</span>
                  </div>
                  <p class="text-xs text-slate-300 font-mono leading-relaxed">${escapeHtml(factText)}</p>
                </div>
              `;
            }).join('');
          } else {
            t2.innerHTML = '<span class="text-slate-500">No episodic memories matched.</span>';
          }
        }

      } catch (e) {
        alert("Retrieval request failed: " + e);
      }
    }

    function refreshAll() {
      loadHealth();
      if (!document.getElementById('tab-content-graph').classList.contains('hidden')) loadGraph();
      if (!document.getElementById('tab-content-journal').classList.contains('hidden')) loadJournal();
      if (!document.getElementById('tab-content-collections').classList.contains('hidden')) loadCollections();
    }

    // Dream Mode Modal Functions
    function openDreamModal() {
      const modal = document.getElementById('dream-modal');
      const box = document.getElementById('dream-status-box');
      if (modal) modal.classList.remove('hidden');
      if (box) {
        box.classList.add('hidden');
        box.innerHTML = '';
      }
      lucide.createIcons();
    }

    function closeDreamModal() {
      const modal = document.getElementById('dream-modal');
      if (modal) modal.classList.add('hidden');
    }

    async function runDreamMode() {
      const btn = document.getElementById('btn-run-dream');
      const statusBox = document.getElementById('dream-status-box');
      const project = document.getElementById('dream-project').value || 'kortext';
      const purgeStale = document.getElementById('dream-purge-stale').checked;

      btn.disabled = true;
      btn.innerHTML = '<span class="animate-spin mr-1">⏳</span> Consolidating...';
      statusBox.classList.remove('hidden');
      statusBox.innerHTML = '<div class="text-purple-400">🌙 Executing consolidation cycle (Pruning, Louvain clustering, Invariant induction)...</div>';

      try {
        const res = await fetch('/api/dream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project: project, purge_stale: purgeStale })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          const r = data.report;
          statusBox.innerHTML = `
            <div class="text-emerald-400 font-bold">✅ Dream Mode completed successfully!</div>
            <div class="space-y-1 text-slate-300 pt-1">
              <div>• Active Facts Remaining: <span class="text-indigo-400">${r.pruned_facts.active_facts_remaining}</span></div>
              <div>• Superseded Facts Pruned: <span class="text-amber-400">${r.pruned_facts.superseded_facts_pruned}</span></div>
              <div>• Contradictions Flagged: <span class="text-rose-400">${r.pruned_facts.contradictions_flagged.length}</span></div>
              <div>• Subsystem Clusters: <span class="text-sky-400">${r.subsystem_clusters}</span></div>
              <div>• Invariant Rules: <span class="text-emerald-400">${r.invariants_inducted}</span></div>
              <div class="text-slate-400 pt-1 text-[10px]">Report: ${r.dream_report_path}</div>
            </div>
          `;
          loadGraph();
        } else {
          statusBox.innerHTML = `<div class="text-rose-400 font-bold">❌ Error: ${data.message}</div>`;
        }
      } catch (err) {
        statusBox.innerHTML = `<div class="text-rose-400 font-bold">❌ Failed to run dream mode: ${err}</div>`;
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="sparkles" class="w-3.5 h-3.5"></i> Run Dream Mode';
        lucide.createIcons();
      }
    }

    let isPhysicsFrozen = true;

    function toggleGraphFreeze() {
      if (!network) return;
      isPhysicsFrozen = !isPhysicsFrozen;
      network.setOptions({ physics: { enabled: !isPhysicsFrozen } });
      setFreezeState(isPhysicsFrozen);
    }

    function setFreezeState(frozen) {
      isPhysicsFrozen = frozen;
      const label = document.getElementById('label-physics-status');
      const dot = document.getElementById('dot-physics');
      const pill = document.getElementById('pill-physics');
      const btn = document.getElementById('btn-toggle-freeze');
      const hudBtn = document.getElementById('btn-hud-freeze');

      if (frozen) {
        if (label) label.innerText = "HARD-FROZEN (60 FPS)";
        if (dot) dot.className = "w-2 h-2 rounded-full bg-emerald-400";
        if (pill) { pill.className = "px-2 py-1 rounded bg-emerald-950/70 text-emerald-400 border border-emerald-700/50"; pill.innerText = "PHYSICS: FROZEN (60 FPS)"; }
        if (btn) btn.className = "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-semibold bg-emerald-950/60 text-emerald-400 border border-emerald-500/40 hover:bg-emerald-900/60 transition";
        if (hudBtn) {
          hudBtn.innerHTML = '<i data-lucide="snowflake" class="w-3.5 h-3.5"></i> Frozen';
          hudBtn.className = 'hud-btn text-emerald-400';
          lucide.createIcons();
        }
      } else {
        if (label) label.innerText = "SIMULATING...";
        if (dot) dot.className = "w-2 h-2 rounded-full bg-amber-400 animate-ping";
        if (pill) { pill.className = "px-2 py-1 rounded bg-amber-950/70 text-amber-400 border border-amber-700/50"; pill.innerText = "PHYSICS: SIMULATING..."; }
        if (btn) btn.className = "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-mono font-semibold bg-amber-950/60 text-amber-400 border border-amber-500/40 hover:bg-amber-900/60 transition";
        if (hudBtn) {
          hudBtn.innerHTML = '<i data-lucide="flame" class="w-3.5 h-3.5 text-amber-400"></i> Simulating';
          hudBtn.className = 'hud-btn text-amber-400';
          lucide.createIcons();
        }
      }
    }

    // Task DAG Client Logic
    let taskNetwork = null;
    let taskNodesDataSet = null;
    let taskEdgesDataSet = null;
    let isTaskPhysicsFrozen = true;

    function zoomTaskGraph(factor) {
      if (!taskNetwork) return;
      const scale = taskNetwork.getScale();
      taskNetwork.moveTo({ scale: scale * factor, animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
    }

    function fitTaskGraph() {
      if (!taskNetwork) return;
      taskNetwork.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
    }

    function toggleTaskFreeze() {
      if (!taskNetwork) return;
      isTaskPhysicsFrozen = !isTaskPhysicsFrozen;
      taskNetwork.setOptions({ physics: { enabled: !isTaskPhysicsFrozen } });
      const st = document.getElementById('task-graph-status');
      const btn = document.getElementById('btn-task-freeze');
      if (st) st.innerText = isTaskPhysicsFrozen ? "PHYSICS: HARD-FROZEN (60 FPS)" : "PHYSICS: SIMULATING...";
      if (btn) {
        btn.innerHTML = isTaskPhysicsFrozen 
          ? '<i data-lucide="snowflake" class="w-3.5 h-3.5"></i> Frozen' 
          : '<i data-lucide="flame" class="w-3.5 h-3.5 text-amber-400"></i> Simulating';
        btn.className = isTaskPhysicsFrozen ? 'hud-btn text-emerald-400' : 'hud-btn text-amber-400';
        lucide.createIcons();
      }
    }

    async function loadTasks() {
      try {
        const res = await fetch('/api/tasks?include_graph=true');
        const data = await res.json();
        if (data.status !== 'ok') {
          console.error("Failed to load tasks:", data.message);
          return;
        }

        const tasks = data.tasks || [];
        const nodes = data.nodes || [];
        const edges = data.edges || [];

        const ready = tasks.filter(t => t.status === 'ready').length;
        const prog = tasks.filter(t => t.status === 'in_progress').length;
        const comp = tasks.filter(t => t.status === 'completed').length;
        const failed = tasks.filter(t => t.status === 'failed' || t.status === 'blocked').length;

        document.getElementById('stat-ready-tasks').textContent = ready;
        document.getElementById('stat-progress-tasks').textContent = prog;
        document.getElementById('stat-completed-tasks').textContent = comp;
        document.getElementById('stat-failed-tasks').textContent = failed;

        renderTaskGraph(nodes, edges);
        renderTasksList(tasks);
      } catch (e) {
        console.error("Error loading tasks:", e);
      }
    }

    function renderTaskGraph(nodes, edges) {
      const container = document.getElementById('task-network-graph');
      if (!container) return;

      taskNodesDataSet = new vis.DataSet(nodes);
      taskEdgesDataSet = new vis.DataSet(formatEdgesNonOverlapping(edges.map(e => ({
        ...e,
        label: e.label || 'DEPENDS_ON'
      }))));

      const options = {
        physics: {
          solver: 'barnesHut',
          barnesHut: {
            gravitationalConstant: -14000,
            centralGravity: 0.10,
            springLength: 160,
            springConstant: 0.04,
            damping: 0.15,
            avoidOverlap: 1.0
          },
          stabilization: { enabled: true, iterations: 140 }
        },
        interaction: { hover: true, tooltipDelay: 150, multiselect: false }
      };

      taskNetwork = new vis.Network(container, { nodes: taskNodesDataSet, edges: taskEdgesDataSet }, options);

      taskNetwork.on("stabilizationIterationsDone", function () {
        taskNetwork.setOptions({ physics: { enabled: false } });
        isTaskPhysicsFrozen = true;
        const st = document.getElementById('task-graph-status');
        if (st) st.innerText = "PHYSICS: HARD-FROZEN (60 FPS)";
      });

      setTimeout(() => {
        if (taskNetwork) {
          taskNetwork.setOptions({ physics: { enabled: false } });
          isTaskPhysicsFrozen = true;
          const st = document.getElementById('task-graph-status');
          if (st) st.innerText = "PHYSICS: HARD-FROZEN (60 FPS)";
        }
      }, 1500);

      taskNetwork.on('click', function(params) {
        if (params.nodes.length > 0) {
          const nodeId = params.nodes[0];
          const connected = taskNetwork.getConnectedNodes(nodeId);
          connected.push(nodeId);
          const connectedSet = new Set(connected);

          const nodeUpdates = taskNodesDataSet.get().map(n => ({
            id: n.id,
            opacity: connectedSet.has(n.id) ? 1.0 : 0.15
          }));
          taskNodesDataSet.update(nodeUpdates);

          const edgeUpdates = taskEdgesDataSet.get().map(e => {
            const isConn = connectedSet.has(e.from) && connectedSet.has(e.to);
            return {
              id: e.id,
              color: isConn 
                ? (e.originalColor || e.color)
                : { color: 'rgba(30, 41, 59, 0.2)', highlight: 'rgba(30, 41, 59, 0.25)', hover: 'rgba(30, 41, 59, 0.3)' },
              width: isConn ? (e.originalWidth || 2.0) : 1
            };
          });
          taskEdgesDataSet.update(edgeUpdates);
        } else {
          const nodeUpdates = taskNodesDataSet.get().map(n => ({ id: n.id, opacity: 1.0 }));
          taskNodesDataSet.update(nodeUpdates);

          const edgeUpdates = taskEdgesDataSet.get().map(e => ({
            id: e.id,
            color: e.originalColor || e.color,
            width: e.originalWidth || 2.0
          }));
          taskEdgesDataSet.update(edgeUpdates);
        }
      });
    }

    function renderTasksList(tasks) {
      const container = document.getElementById('tasks-container');
      if (!container) return;

      if (!tasks || tasks.length === 0) {
        container.innerHTML = '<div class="text-slate-500 py-12 text-center text-xs">No active tasks in Task DAG. Click "Create Task" above.</div>';
        return;
      }

      const statusBadge = {
        'ready': 'bg-sky-500/10 text-sky-400 border-sky-500/30',
        'in_progress': 'bg-amber-950/80 text-amber-300 border-amber-600/60 font-semibold',
        'completed': 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
        'pending': 'bg-slate-700/20 text-slate-400 border-slate-700/40',
        'failed': 'bg-rose-500/10 text-rose-400 border-rose-500/30',
        'blocked': 'bg-red-900/20 text-red-400 border-red-800/40',
      };

      container.innerHTML = tasks.map(t => {
        const badge = statusBadge[t.status] || statusBadge['pending'];
        return `
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:border-slate-700 transition">
            <div class="space-y-1">
              <div class="flex items-center gap-2">
                <span class="font-mono text-xs font-semibold text-slate-400">${t.id}</span>
                <span class="text-xs font-mono px-2 py-0.5 rounded border ${badge} uppercase font-semibold">${t.status}</span>
                <span class="text-xs font-mono text-slate-500">Complexity: ${t.complexity}/10</span>
                <span class="text-xs font-mono text-slate-500">Assigned: ${t.assigned_to}</span>
              </div>
              <h4 class="font-medium text-white text-sm">${t.title}</h4>
              ${t.description ? `<p class="text-xs text-slate-400">${t.description}</p>` : ''}
              ${t.depends_on && t.depends_on.length > 0 ? `<div class="text-[11px] font-mono text-indigo-400">Depends on: ${t.depends_on.join(', ')}</div>` : ''}
              ${t.last_error ? `<div class="text-[11px] font-mono text-rose-400">Last Error: ${t.last_error}</div>` : ''}
            </div>
            <div class="flex items-center gap-2 self-end md:self-center">
              ${t.status !== 'in_progress' && t.status !== 'completed' ? `
                <button onclick="updateTaskStatus('${t.id}', 'in_progress')" class="px-2.5 py-1 text-xs rounded bg-amber-950/80 hover:bg-amber-900/90 text-amber-300 border border-amber-600/60 font-mono font-semibold transition">Start</button>
              ` : ''}
              ${t.status !== 'completed' ? `
                <button onclick="updateTaskStatus('${t.id}', 'completed')" class="px-2.5 py-1 text-xs rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-mono transition">Done</button>
              ` : ''}
              ${t.status !== 'failed' && t.status !== 'completed' ? `
                <button onclick="updateTaskStatus('${t.id}', 'failed', 'Marked failed via UI')" class="px-2.5 py-1 text-xs rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 font-mono transition">Fail</button>
              ` : ''}
            </div>
          </div>
        `;
      }).join('');
    }

    async function updateTaskStatus(taskId, status, error = null) {
      try {
        const res = await fetch('/api/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'update_status', task_id: taskId, status: status, error: error })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          loadTasks();
        } else {
          alert('Failed to update task: ' + (data.message || 'unknown error'));
        }
      } catch (e) {
        console.error("Task update error:", e);
      }
    }

    function openCreateTaskModal() {
      const modal = document.getElementById('modal-create-task');
      if (modal) modal.classList.remove('hidden');
    }

    function closeCreateTaskModal() {
      const modal = document.getElementById('modal-create-task');
      if (modal) modal.classList.add('hidden');
    }

    async function submitCreateTask() {
      const title = document.getElementById('task-input-title').value.trim();
      const desc = document.getElementById('task-input-desc').value.trim();
      const comp = parseInt(document.getElementById('task-input-comp').value, 10) || 1;
      const assign = document.getElementById('task-input-assign').value.trim() || 'primary';
      const rawDeps = document.getElementById('task-input-deps').value.trim();
      const deps = rawDeps ? rawDeps.split(',').map(s => s.trim()).filter(Boolean) : null;

      if (!title) {
        alert('Please enter a task title');
        return;
      }

      try {
        const res = await fetch('/api/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'create',
            title: title,
            description: desc,
            complexity: comp,
            assigned_to: assign,
            depends_on: deps
          })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          closeCreateTaskModal();
          document.getElementById('task-input-title').value = '';
          document.getElementById('task-input-desc').value = '';
          document.getElementById('task-input-deps').value = '';
          loadTasks();
        } else {
          alert('Task creation failed: ' + (data.message || 'unknown error'));
        }
      } catch (e) {
        console.error("Create task error:", e);
      }
    }

    // MINJA Quarantine Client Logic
    async function loadQuarantine() {
      try {
        const res = await fetch('/api/quarantine');
        const data = await res.json();
        if (data.status !== 'ok') return;

        const count = data.quarantine_count || 0;
        const countLabel = document.getElementById('quarantine-count-label');
        if (countLabel) countLabel.innerText = `${count} Violations Detected`;

        const container = document.getElementById('quarantine-list');
        if (!container) return;

        if (!data.items || data.items.length === 0) {
          container.innerHTML = '<div class="text-slate-500 py-12 text-center text-xs">No adversarial violations detected. Causal memory is clean.</div>';
          return;
        }

        container.innerHTML = data.items.map(item => `
          <div class="bg-slate-950 border border-rose-500/20 rounded-xl p-3.5 space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-rose-400 font-semibold font-mono text-[11px]">${item.reason || 'Security Violation'}</span>
              <span class="text-slate-500 font-mono text-[10px]">${item.timestamp || ''}</span>
            </div>
            <div class="text-slate-300 font-mono text-xs bg-slate-900 p-2.5 rounded-lg border border-slate-800">
              ${item.fact || item.subject || ''}
            </div>
          </div>
        `).join('');
      } catch (e) {
        console.error("Quarantine load error:", e);
      }
    }

    async function clearQuarantine() {
      if (!confirm("Are you sure you want to clear the quarantine log? All quarantined adversarial payloads will be purged.")) return;
      try {
        const res = await fetch('/api/quarantine', { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'ok') {
          alert(`Quarantine cleared successfully. (${data.cleared_count || 0} payloads purged)`);
          loadQuarantine();
        } else {
          alert('Failed to clear quarantine: ' + (data.message || 'unknown error'));
        }
      } catch (e) {
        console.error("Quarantine clear error:", e);
        alert('Error clearing quarantine: ' + e);
      }
    }

    // Telemetry HUD Client Logic
    async function loadTelemetry() {
      try {
        const res = await fetch('/api/telemetry');
        const data = await res.json();
        if (data.status === 'ok' && data.telemetry) {
          const t = data.telemetry;
          const savEl = document.getElementById('hud-savings');
          const rssEl = document.getElementById('hud-rss');
          const latEl = document.getElementById('hud-lat');
          const invEl = document.getElementById('hud-invariants');
          if (savEl) savEl.innerText = t.token_search_savings || 'Active (AST Index)';
          if (rssEl) rssEl.innerText = `${t.substrate_ram_rss_mb} MB RSS`;
          if (latEl) latEl.innerText = `${t.falkordb_latency_ms} ms`;
          if (invEl && t.active_invariants !== undefined) invEl.innerText = `${t.active_invariants} Verified`;
        }
      } catch (e) {
        console.error("Telemetry load error:", e);
      }
    }

    // Initial Load
    document.addEventListener('DOMContentLoaded', () => {
      lucide.createIcons();
      loadHealth();
      loadTelemetry();
      populateGraphSelector().then(() => loadGraph());
      populateRetrievalCollections();
      setInterval(loadHealth, 15000); // 15s health heartbeat
    });
