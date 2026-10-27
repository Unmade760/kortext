"""
Unit tests for Kortext CLI Subcommands: grammars, scip, clean-graphs, and watch.
"""

from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch
import pytest

from kortext import cli


def test_grammars_parser_registration():
    parser = argparse.ArgumentParser()
    # Test through main parser or subcommand parser
    with patch("sys.argv", ["kortext", "grammars", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 0


def test_grammars_enable_cpp():
    args = argparse.Namespace(enable="cpp", disable=None, status=False)
    with patch("subprocess.run") as mock_run, \
         patch("kortext.chunking.languages.print_language_status") as mock_status:
        cli.cmd_grammars(args)
        mock_run.assert_called_once_with(["uv", "pip", "install", "tree-sitter-c", "tree-sitter-cpp"], check=True)
        mock_status.assert_called_once()


def test_grammars_enable_all():
    args = argparse.Namespace(enable="all", disable=None, status=False)
    with patch("subprocess.run") as mock_run, \
         patch("kortext.chunking.languages.print_language_status") as mock_status:
        cli.cmd_grammars(args)
        mock_run.assert_called_once_with(
            ["uv", "pip", "install", "tree-sitter-c", "tree-sitter-cpp", "tree-sitter-java", "tree-sitter-kotlin", "tree-sitter-swift", "tree-sitter-c-sharp"],
            check=True,
        )
        mock_status.assert_called_once()


def test_grammars_enable_custom():
    args = argparse.Namespace(enable="rust", disable=None, status=False)
    with patch("subprocess.run") as mock_run, \
         patch("kortext.chunking.languages.print_language_status") as mock_status:
        cli.cmd_grammars(args)
        mock_run.assert_called_once_with(["uv", "pip", "install", "tree-sitter-rust"], check=True)
        mock_status.assert_called_once()


def test_grammars_disable():
    args = argparse.Namespace(enable=None, disable="swift", status=False)
    with patch("subprocess.run") as mock_run, \
         patch("kortext.chunking.languages.print_language_status") as mock_status:
        cli.cmd_grammars(args)
        mock_run.assert_called_once_with(["uv", "pip", "uninstall", "tree-sitter-swift"], check=True)
        mock_status.assert_called_once()


def test_grammars_default_status():
    args = argparse.Namespace(enable=None, disable=None, status=True)
    with patch("subprocess.run") as mock_run, \
         patch("kortext.chunking.languages.print_language_status") as mock_status:
        cli.cmd_grammars(args)
        mock_run.assert_not_called()
        mock_status.assert_called_once()


def test_scip_help():
    with patch("sys.argv", ["kortext", "scip", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 0


def test_scip_explicit_target(capsys):
    args = argparse.Namespace(target="index.scip", auto=False, graph="kortext_symbols", no_purge=False)
    mock_importer_cls = MagicMock()
    mock_importer_instance = MagicMock()
    mock_importer_cls.return_value = mock_importer_instance
    mock_importer_instance.ingest_index.return_value = {
        "documents_indexed": 10,
        "symbols_indexed": 50,
        "references_indexed": 120,
        "relationships_indexed": 30,
        "duration_seconds": 1.25,
    }

    with patch("kortext.symbols.scip.SCIPImporter", mock_importer_cls):
        cli.cmd_scip(args)
        mock_importer_cls.assert_called_once_with(graph_name="kortext_symbols")
        mock_importer_instance.ingest_index.assert_called_once_with("index.scip", purge_existing=True)

    captured = capsys.readouterr()
    assert "SCIP Ingestion Complete: 10 documents, 50 symbols" in captured.out


def test_scip_auto_mode(capsys):
    args = argparse.Namespace(target=".", auto=True, graph="custom_symbols", no_purge=True)
    mock_auto = MagicMock(return_value={
        "status": "success",
        "documents_indexed": 5,
        "symbols_indexed": 20,
        "references_indexed": 40,
        "relationships_indexed": 8,
        "duration_seconds": 0.8,
    })

    with patch("kortext.symbols.scip.auto_index_and_ingest", mock_auto):
        cli.cmd_scip(args)
        mock_auto.assert_called_once_with(".", graph_name="custom_symbols", purge_existing=False)

    captured = capsys.readouterr()
    assert "SCIP Ingestion Complete: 5 documents, 20 symbols" in captured.out


def test_scip_auto_missing_indexer(capsys):
    args = argparse.Namespace(target=".", auto=True, graph="kortext_symbols", no_purge=False)
    mock_auto = MagicMock(return_value={
        "status": "missing_indexer",
        "message": "SCIP indexer not found",
        "install_hint": "npm install -g @sourcegraph/scip-typescript",
    })

    with patch("kortext.symbols.scip.auto_index_and_ingest", mock_auto):
        cli.cmd_scip(args)

    captured = capsys.readouterr()
    assert "SCIP indexer not found" in captured.out
    assert "npm install -g @sourcegraph/scip-typescript" in captured.out


def test_clean_graphs(capsys):
    args = argparse.Namespace()
    mock_redis = MagicMock()
    mock_redis.execute_command.side_effect = lambda cmd, *cmd_args: (
        ["prod_graph", "test_graph_1", "kortext_symbols", "my_test_2"] if cmd == "GRAPH.LIST" else None
    )
    mock_client = MagicMock()
    mock_client.get_redis.return_value = mock_redis

    with patch("kortext.falkordb_client.get_shared_falkordb_client", return_value=mock_client):
        cli.cmd_clean_graphs(args)

    # Should delete the 2 graphs with "test" in name
    deleted_calls = [c for c in mock_redis.execute_command.call_args_list if c[0][0] == "GRAPH.DELETE"]
    assert len(deleted_calls) == 2
    deleted_names = [c[0][1] for c in deleted_calls]
    assert "test_graph_1" in deleted_names
    assert "my_test_2" in deleted_names

    captured = capsys.readouterr()
    assert "Deleted 2 test graph(s)" in captured.out


def test_watch_command():
    args = argparse.Namespace(root="/test/dir", collection="test_col")
    with patch("asyncio.run") as mock_async_run, \
         patch("kortext.watcher.start_watcher", new_callable=MagicMock) as mock_start_watcher:
        cli.cmd_watch(args)
        mock_async_run.assert_called_once()


def test_cmd_impact_default_prints_markdown_summary(capsys):
    args = argparse.Namespace(symbol="MyEngine", depth=2, direction="upstream", json=False)
    mock_seeker = MagicMock()
    mock_seeker.trace_impact.return_value = json.dumps({
        "symbol": "MyEngine",
        "direction": "upstream",
        "max_depth": 2,
        "formatted_summary": "### Symbol blast radius: `MyEngine`\n- Total affected sites: 3",
    })

    with patch("kortext.cli.SymbolSeekEngine", return_value=mock_seeker):
        cli.cmd_impact(args)
        mock_seeker.trace_impact.assert_called_once_with("MyEngine", depth=2, direction="upstream")

    captured = capsys.readouterr()
    assert "### Symbol blast radius: `MyEngine`" in captured.out
    assert "- Total affected sites: 3" in captured.out
    assert '{\n  "symbol":' not in captured.out


def test_cmd_impact_json_flag_prints_raw_json(capsys):
    raw_payload = json.dumps({
        "symbol": "MyEngine",
        "formatted_summary": "summary",
    }, indent=2)
    args = argparse.Namespace(symbol="MyEngine", depth=2, direction="upstream", json=True)
    mock_seeker = MagicMock()
    mock_seeker.trace_impact.return_value = raw_payload

    with patch("kortext.cli.SymbolSeekEngine", return_value=mock_seeker):
        cli.cmd_impact(args)

    captured = capsys.readouterr()
    assert '"symbol": "MyEngine"' in captured.out


def test_cmd_impact_parser_registration():
    with patch("sys.argv", ["kortext", "impact", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 0


def test_cmd_impact_fallback_when_invalid_json(capsys):
    args = argparse.Namespace(symbol="BrokenOutput", depth=1)
    mock_seeker = MagicMock()
    mock_seeker.trace_impact.return_value = "Non-json string output"

    with patch("kortext.cli.SymbolSeekEngine", return_value=mock_seeker):
        cli.cmd_impact(args)

    captured = capsys.readouterr()
    assert "Non-json string output" in captured.out


def test_cmd_impact_fallback_when_no_formatted_summary(capsys):
    args = argparse.Namespace(symbol="NoSummary", depth=1)
    mock_seeker = MagicMock()
    mock_seeker.trace_impact.return_value = json.dumps({"raw_field": 123})

    with patch("kortext.cli.SymbolSeekEngine", return_value=mock_seeker):
        cli.cmd_impact(args)

    captured = capsys.readouterr()
    assert '{"raw_field": 123}' in captured.out


def test_cmd_start_invokes_start_kortext():
    args = argparse.Namespace()
    # Windows takes the start_substrates() path instead of the shell script.
    with patch("platform.system", return_value="Linux"), patch("subprocess.run") as mock_run:
        cli.cmd_start(args)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "bash"
        assert cmd[1].endswith("start_kortext.sh")


def test_cmd_stop_invokes_stop_kortext():
    args = argparse.Namespace()
    # Windows takes the start_substrates() path instead of the shell script.
    with patch("platform.system", return_value="Linux"), patch("subprocess.run") as mock_run:
        cli.cmd_stop(args)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "bash"
        assert cmd[1].endswith("stop_kortext.sh")

