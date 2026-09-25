"""
Cerebrum Unified CLI: The Cognitive OS & Code Intelligence Gateway.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from cerebrum.symbols.seek import SymbolSeekEngine
from cerebrum.dream import DreamEngine


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

    socket_file = Path.home() / ".cerebrum" / "run" / "falkordb.sock"
    falkor_sock = socket_file.is_socket()
    falkor_tcp  = check_tcp("127.0.0.1", 6379)
    falkor = falkor_sock or falkor_tcp

    qdrant_embedded = (Path.home() / ".cerebrum" / "qdrant").is_dir()
    qdrant_remote   = check_tcp("127.0.0.1", 6333)

    omlx = check_tcp("127.0.0.1", 8000)

    print("=== Cerebrum Substrate Health (Zero-Docker) ===")
    channel = "Unix Socket" if falkor_sock else "TCP :6379"
    print(f"  FalkorDB (Graph Memory) [{channel}]       : {'✅ ONLINE' if falkor else '❌ OFFLINE'}")
    if qdrant_embedded:
        print(f"  Qdrant   (Vector Memory)[Embedded Rust]  : ✅ ONLINE (~/.cerebrum/qdrant)")
    else:
        print(f"  Qdrant   (Vector Memory)[:6333]          : {'✅ ONLINE' if qdrant_remote else '❌ OFFLINE'}")
    print(f"  oMLX     (Local Embedder)[:8000]         : {'✅ ONLINE' if omlx else '❌ OFFLINE'}")


def cmd_start(args):
    """Starts native FalkorDB and embedded substrates."""
    import subprocess
    script = Path(__file__).resolve().parent.parent / "scripts" / "start_cerebrum.sh"
    subprocess.run(["bash", str(script)], check=True)


def cmd_stop(args):
    """Stops native FalkorDB and embedded substrates."""
    import subprocess
    script = Path(__file__).resolve().parent.parent / "scripts" / "stop_cerebrum.sh"
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
    result = seeker.trace_impact(args.symbol, depth=args.depth)
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
    from cerebrum.ingest import ingest
    target_dir = args.root or os.getcwd()
    asyncio.run(ingest(root=target_dir, force=args.force))


def cmd_server(args):
    """Run FastMCP Server."""
    from cerebrum.server import main as server_main
    server_main()


def cmd_dashboard(args):
    """Run Cerebrum Dashboard."""
    from cerebrum.dashboard.app import main as dashboard_main
    dashboard_main()


def main():
    parser = argparse.ArgumentParser(
        prog="cerebrum",
        description="Cerebrum: Cognitive OS, Memory Hierarchy & Anti-Ripgrep Engine",
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
    p_impact.set_defaults(func=cmd_impact)

    # dream
    p_dream = subparsers.add_parser("dream", help="Trigger Cognitive Dream Mode")
    p_dream.add_argument("--project", default="cerebrum", help="Project label")
    p_dream.add_argument("--purge-stale", action="store_true", default=True, help="Purge stale facts")
    p_dream.add_argument("--dry-run", action="store_true", help="Preview without modifying")
    p_dream.set_defaults(func=cmd_dream)

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Batch ingest code into Qdrant & FalkorDB")
    p_ingest.add_argument("--root", default=None, help="Root directory path")
    p_ingest.add_argument("--force", action="store_true", help="Force re-indexing")
    p_ingest.set_defaults(func=cmd_ingest)

    # server
    p_server = subparsers.add_parser("server", help="Start FastMCP server daemon")
    p_server.set_defaults(func=cmd_server)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Start visual dashboard on :8004")
    p_dash.set_defaults(func=cmd_dashboard)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
