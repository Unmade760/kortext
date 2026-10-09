"""
Kortext Unified CLI: The Cognitive Knowledge OS & Code Intelligence Gateway.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from kortext.symbols.seek import SymbolSeekEngine
from kortext.dream import DreamEngine


def cmd_status(args):
    """Checks native substrate health across FalkorDB, Embedded Qdrant, and oMLX."""
    import socket
    from pathlib import Path

    def check_tcp(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except Exception:
            return False

    kortext_home = Path(os.getenv("KORTEXT_HOME", os.getenv("CEREBRUM_HOME", str(Path.home() / ".kortext" if (Path.home() / ".kortext").exists() or not (Path.home() / ".cerebrum").exists() else Path.home() / ".cerebrum"))))
    socket_file = kortext_home / "run" / "falkordb.sock"
    if not socket_file.exists():
        legacy_sock = Path.home() / ".cerebrum" / "run" / "falkordb.sock"
        if legacy_sock.exists():
            socket_file = legacy_sock
    falkor_sock = socket_file.is_socket()
    falkor_tcp  = check_tcp("127.0.0.1", 6379)
    falkor = falkor_sock or falkor_tcp

    qpath = kortext_home / "qdrant"
    if not qpath.exists() and (Path.home() / ".cerebrum" / "qdrant").exists():
        qpath = Path.home() / ".cerebrum" / "qdrant"
    qdrant_embedded = qpath.is_dir()
    qdrant_remote   = check_tcp("127.0.0.1", 6333)

    omlx = check_tcp("127.0.0.1", 8000)

    print("=== Kortext Substrate Health (Zero-Docker) ===")
    channel = "Unix Socket" if falkor_sock else "TCP :6379"
    print(f"  FalkorDB (Graph Memory) [{channel}]       : {'✅ ONLINE' if falkor else '❌ OFFLINE'}")
    if qdrant_embedded:
        print(f"  Qdrant   (Vector Memory)[Embedded Rust]  : ✅ ONLINE ({qpath})")
    else:
        print(f"  Qdrant   (Vector Memory)[:6333]          : {'✅ ONLINE' if qdrant_remote else '❌ OFFLINE'}")
    print(f"  oMLX     (Local Embedder)[:8000]         : {'✅ ONLINE' if omlx else '❌ OFFLINE'}")


def cmd_start(args):
    """Starts native FalkorDB and embedded substrates."""
    import subprocess
    script = Path(__file__).resolve().parent.parent / "scripts" / "start_kortext.sh"
    subprocess.run(["bash", str(script)], check=True)


def cmd_stop(args):
    """Stops native FalkorDB and embedded substrates."""
    import subprocess
    script = Path(__file__).resolve().parent.parent / "scripts" / "stop_kortext.sh"
    subprocess.run(["bash", str(script)], check=True)


def cmd_install(args):
    """Installs plugin, skills, agents, and substrate daemons."""
    import subprocess
    script = Path(__file__).resolve().parent.parent / "scripts" / "install_plugin.py"
    cmd = [sys.executable, str(script)]
    if getattr(args, "all", False):
        cmd.append("--all")
    subprocess.run(cmd, check=True)


def cmd_seek(args):
    """Deterministic Anti-Ripgrep AST Symbol Seek."""
    seeker = SymbolSeekEngine()
    result = seeker.seek_symbol(args.symbol)
    print(result)


def cmd_impact(args):
    """Multi-Hop Call Graph Blast Radius Traverser."""
    seeker = SymbolSeekEngine()
    direction = getattr(args, "direction", "upstream")
    result = seeker.trace_impact(args.symbol, depth=args.depth, direction=direction)

    output_json = getattr(args, "json", False)
    if not output_json:
        try:
            data = json.loads(result) if isinstance(result, str) else result
            if isinstance(data, dict) and "formatted_summary" in data:
                print(data["formatted_summary"])
                return
        except Exception:
            pass
    print(result)



def cmd_dream(args):
    """Cognitive Dream Mode REM Consolidation."""
    engine = DreamEngine()
    res = asyncio.run(engine.run_dream_cycle(
        project=args.project,
        purge_stale=args.purge_stale,
        dry_run=args.dry_run,
    ))
    print(res["markdown_report"])


def cmd_ingest(args):
    """Batch AST Ingestion."""
    from kortext.ingest import ingest
    target_dir = args.root or os.getcwd()
    asyncio.run(ingest(root=target_dir, force=args.force))


def cmd_server(args):
    """Run FastMCP Server."""
    from kortext.server import main as server_main
    server_main()


def cmd_dashboard(args):
    """Run Kortext Dashboard."""
    from kortext.dashboard.app import main as dashboard_main
    dashboard_main()


def cmd_grammars(args):
    """Manage Tree-sitter AST language grammars."""
    import subprocess
    from kortext.chunking.languages import print_language_status

    enable = getattr(args, "enable", None)
    disable = getattr(args, "disable", None)

    if enable:
        mapping = {
            "cpp": ["tree-sitter-c", "tree-sitter-cpp"],
            "jvm": ["tree-sitter-java", "tree-sitter-kotlin"],
            "swift": ["tree-sitter-swift"],
            "csharp": ["tree-sitter-c-sharp"],
            "all": [
                "tree-sitter-c",
                "tree-sitter-cpp",
                "tree-sitter-java",
                "tree-sitter-kotlin",
                "tree-sitter-swift",
                "tree-sitter-c-sharp",
            ],
        }
        pkgs = mapping.get(enable, [f"tree-sitter-{enable}"])
        subprocess.run(["uv", "pip", "install", *pkgs], check=True)
    elif disable:
        pkg = f"tree-sitter-{disable}"
        subprocess.run(["uv", "pip", "uninstall", pkg], check=True)

    print_language_status()


def cmd_scip(args):
    """Ingest SCIP Protobuf index into FalkorDB."""
    from kortext.symbols.scip import auto_index_and_ingest, SCIPImporter

    target = getattr(args, "target", ".") or "."
    default_graph = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))
    graph = getattr(args, "graph", default_graph) or default_graph
    purge_existing = not getattr(args, "no_purge", False)

    if getattr(args, "auto", False):
        result = auto_index_and_ingest(target, graph_name=graph, purge_existing=purge_existing)
        if result.get("status") == "missing_indexer":
            print(f"⚠️  {result.get('message', 'SCIP indexer not found')}")
            if result.get("install_hint"):
                print(f"   Install it via: {result['install_hint']}")
            return
        elif result.get("status") == "error":
            print(f"❌ Error: {result.get('message', 'SCIP auto-indexing failed')}")
            return
    else:
        importer = SCIPImporter(graph_name=graph)
        result = importer.ingest_index(target, purge_existing=purge_existing)

    print(
        f"✅ SCIP Ingestion Complete: {result.get('documents_indexed', 0)} documents, "
        f"{result.get('symbols_indexed', 0)} symbols, {result.get('references_indexed', 0)} references, "
        f"{result.get('relationships_indexed', 0)} inter-symbol relations in {result.get('duration_seconds', 0)}s."
    )


def cmd_clean_graphs(args):
    """Purge lingering test graphs from FalkorDB."""
    from kortext.falkordb_client import get_shared_falkordb_client

    try:
        r = get_shared_falkordb_client().get_redis()
        graphs = [g for g in (r.execute_command("GRAPH.LIST") or []) if "test" in str(g).lower()]
        for g in graphs:
            r.execute_command("GRAPH.DELETE", g)
        print(f"✅ Deleted {len(graphs)} test graph(s): {graphs}")
    except Exception as exc:
        print(f"❌ Failed to clean test graphs: {exc}")


def cmd_watch(args):
    """Start real-time incremental file watcher daemon."""
    root = getattr(args, "root", ".") or "."
    collection = getattr(args, "collection", None)
    try:
        from kortext.watcher import run_watcher
        kwargs = {"watch_root": root}
        if collection:
            kwargs["collection"] = collection
        run_watcher(**kwargs)
    except (ImportError, AttributeError):
        from kortext.watcher import start_watcher, COLLECTION
        coll = collection or COLLECTION
        asyncio.run(start_watcher(watch_root=root, collection=coll))


def main():
    parser = argparse.ArgumentParser(
        prog="kortext",
        description="Kortext Knowledge OS: Cognitive Memory Hierarchy, AST Intelligence & Anti-Ripgrep Engine",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # start
    p_start = subparsers.add_parser("start", help="Start native substrates (FalkorDB, Embedded Qdrant)")
    p_start.set_defaults(func=cmd_start)

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop native substrates")
    p_stop.set_defaults(func=cmd_stop)

    # install
    p_install = subparsers.add_parser("install", help="Install Antigravity plugins, skills, and daemons")
    p_install.add_argument("--all", action="store_true", help="Install all integrations, LaunchAgents, and daemons")
    p_install.set_defaults(func=cmd_install)

    # status
    p_status = subparsers.add_parser("status", help="Check status of memory engines")
    p_status.set_defaults(func=cmd_status)

    # seek
    p_seek = subparsers.add_parser("seek", help="Deterministic AST symbol seek")
    p_seek.add_argument("symbol", help="Symbol identifier name")
    p_seek.set_defaults(func=cmd_seek)

    # impact
    p_impact = subparsers.add_parser("impact", help="Trace caller blast radius")
    p_impact.add_argument("symbol", help="Symbol identifier name")
    p_impact.add_argument("--depth", type=int, default=3, help="Max traversal depth")
    p_impact.add_argument("--direction", default="upstream", choices=["upstream", "downstream"], help="Traversal direction: upstream (callers) or downstream (callees)")
    p_impact.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted markdown summary")
    p_impact.set_defaults(func=cmd_impact)

    # dream
    p_dream = subparsers.add_parser("dream", help="Trigger Cognitive Dream Mode")
    p_dream.add_argument("--project", default="kortext", help="Project label")
    p_dream.add_argument("--purge-stale", action="store_true", default=True, help="Purge stale facts")
    p_dream.add_argument("--dry-run", action="store_true", help="Preview without modifying")
    p_dream.set_defaults(func=cmd_dream)

    # ingest / index
    p_ingest = subparsers.add_parser("ingest", aliases=["index"], help="Batch ingest code into Qdrant & FalkorDB")
    p_ingest.add_argument("--root", default=None, help="Root directory path")
    p_ingest.add_argument("--force", action="store_true", help="Force re-indexing")
    p_ingest.set_defaults(func=cmd_ingest)

    # server
    p_server = subparsers.add_parser("server", help="Start FastMCP server daemon")
    p_server.set_defaults(func=cmd_server)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Start visual dashboard on :8004")
    p_dash.set_defaults(func=cmd_dashboard)

    # grammars
    p_grammars = subparsers.add_parser("grammars", help="Manage Tree-sitter language grammars")
    p_grammars.add_argument("--enable", help="Language or family to enable (cpp, jvm, swift, csharp, all, or custom)")
    p_grammars.add_argument("--disable", help="Language grammar to uninstall")
    p_grammars.add_argument("--status", action="store_true", help="Display language status")
    p_grammars.set_defaults(func=cmd_grammars)

    # scip
    default_scip_graph = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))
    p_scip = subparsers.add_parser("scip", help="Ingest SCIP Protobuf index into FalkorDB")
    p_scip.add_argument("target", nargs="?", default=".", help="Path to index.scip or project root (default: '.')")
    p_scip.add_argument("--auto", action="store_true", help="Auto-detect project type and generate index.scip if missing")
    p_scip.add_argument("--graph", default=default_scip_graph, help=f"FalkorDB symbols graph name (default: '{default_scip_graph}')")
    p_scip.add_argument("--no-purge", action="store_true", help="Do not purge previous file relations")
    p_scip.set_defaults(func=cmd_scip)

    # clean-graphs
    p_clean = subparsers.add_parser("clean-graphs", help="Purge lingering test graphs from FalkorDB")
    p_clean.set_defaults(func=cmd_clean_graphs)

    # watch
    p_watch = subparsers.add_parser("watch", help="Start real-time incremental file watcher daemon")
    p_watch.add_argument("--root", default=".", help="Directory to monitor (default: '.')")
    p_watch.add_argument("--collection", default=None, help="Qdrant collection name")
    p_watch.set_defaults(func=cmd_watch)

    # help
    p_help = subparsers.add_parser("help", help="Show this help message")
    p_help.set_defaults(func=lambda _: parser.print_help())

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
