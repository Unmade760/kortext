import pytest
from kortext.chunking import config_splitter, markdown_splitter
from kortext.chunking.token_utils import count_tokens


def test_config_splitter_uses_canonical_count_tokens():
    assert not hasattr(config_splitter, "_fallback_count_tokens"), (
        "config_splitter still has _fallback_count_tokens; should import count_tokens"
    )
    assert getattr(config_splitter, "count_tokens") is count_tokens

    splitter = config_splitter.ConfigSectionSplitter(max_tokens=64)
    data = {"key1": "value1", "key2": "value2" * 50}
    import json
    chunks = splitter.split_config(json.dumps(data), file_path="config.json")
    assert len(chunks) >= 1
    for c in chunks:
        assert "text" in c
        assert "chunk_type" in c


def test_markdown_splitter_uses_canonical_count_tokens():
    assert not hasattr(markdown_splitter, "_fallback_count_tokens"), (
        "markdown_splitter still has _fallback_count_tokens; should import count_tokens"
    )
    assert getattr(markdown_splitter, "count_tokens") is count_tokens

    splitter = markdown_splitter.MarkdownSectionSplitter(max_tokens=64)
    md_text = "# Header 1\nSome introductory content.\n\n## Subheader 1.1\nMore content that goes on."
    chunks = splitter.split_markdown(md_text, file_path="doc.md")
    assert len(chunks) >= 1
    for c in chunks:
        assert "text" in c
        assert "chunk_type" in c


class ParserWrapper:
    def __init__(self, parser):
        self._parser = parser
        self.call_count = 0

    def parse(self, *args, **kwargs):
        self.call_count += 1
        return self._parser.parse(*args, **kwargs)


def test_ast_splitter_extract_symbols_accepts_tree_and_avoids_reparse():
    from kortext.chunking.ast_splitter import ASTCodeSplitter
    from kortext.chunking.languages import PY_LANG

    splitter = ASTCodeSplitter(language=PY_LANG)
    code = "def sample():\n    return 42\n"
    source_bytes = code.encode("utf-8")
    tree = splitter.parser.parse(source_bytes)

    wrapper = ParserWrapper(splitter.parser)
    splitter.parser = wrapper

    ast_info = splitter.extract_symbols_and_references(
        code, file_path="test_sample.py", tree=tree, source_bytes=source_bytes
    )
    assert wrapper.call_count == 0
    assert "declarations" in ast_info
    assert any(d.get("name") == "sample" for d in ast_info["declarations"])


def test_ast_splitter_split_text_reuses_tree_for_symbols():
    from kortext.chunking.ast_splitter import ASTCodeSplitter, clear_ast_cache
    from kortext.chunking.languages import PY_LANG

    clear_ast_cache()
    splitter = ASTCodeSplitter(language=PY_LANG)
    code = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"

    wrapper = ParserWrapper(splitter.parser)
    splitter.parser = wrapper

    chunks = splitter.split_text(code, file_path="test_split.py")
    assert len(chunks) >= 1
    # parser.parse should only be called once, not twice!
    assert wrapper.call_count == 1


def test_ast_splitter_cache_reuses_parsed_ast_between_symbols_and_split():
    from kortext.chunking.ast_splitter import ASTCodeSplitter, clear_ast_cache
    from kortext.chunking.languages import PY_LANG

    clear_ast_cache()
    code = "class Calculator:\n    def add(self, a, b):\n        return a + b\n"
    file_path = "test_calc.py"

    splitter1 = ASTCodeSplitter(language=PY_LANG)
    wrapper1 = ParserWrapper(splitter1.parser)
    splitter1.parser = wrapper1

    ast_info = splitter1.extract_symbols_and_references(code, file_path=file_path)
    assert wrapper1.call_count == 1
    assert any(d.get("name") == "Calculator" for d in ast_info.get("declarations", []))

    # Second splitter representing subsequent chunking step
    splitter2 = ASTCodeSplitter(language=PY_LANG)
    wrapper2 = ParserWrapper(splitter2.parser)
    splitter2.parser = wrapper2

    chunks = splitter2.split_code(code, file_path=file_path)
    assert len(chunks) >= 1
    # Should reuse cached AST: parse should NOT be called on splitter2!
    assert wrapper2.call_count == 0


def test_ast_extractor_extracts_java_and_swift_imports():
    from kortext.chunking.ast_extractor import extract_symbols_and_references
    from kortext.chunking.languages import LANG_MAP

    if ".java" in LANG_MAP:
        java_code = "import java.util.List;\nimport static java.lang.Math.PI;\nimport java.util.*;\npublic class Foo {}"
        res_java = extract_symbols_and_references(LANG_MAP[".java"], java_code, file_path="Foo.java")
        imps_java = res_java.get("imports", [])
        assert any(i["symbol"] == "List" and i["module"] == "java.util.List" for i in imps_java)
        assert any(i["symbol"] == "PI" and i["module"] == "java.lang.Math.PI" for i in imps_java)
        assert any(i["symbol"] == "*" and i["module"] == "java.util.*" for i in imps_java)

    if ".swift" in LANG_MAP:
        swift_code = "import Foundation\nimport struct SwiftUI.View\nclass Bar {}"
        res_swift = extract_symbols_and_references(LANG_MAP[".swift"], swift_code, file_path="Bar.swift")
        imps_swift = res_swift.get("imports", [])
        assert any(i["symbol"] == "Foundation" and i["module"] == "Foundation" for i in imps_swift)
        assert any(i["symbol"] == "View" and i["module"] == "SwiftUI.View" for i in imps_swift)


def test_ast_splitter_split_code_accepts_tree_and_ast_info():
    from kortext.chunking.ast_splitter import ASTCodeSplitter
    from kortext.chunking.languages import PY_LANG

    splitter = ASTCodeSplitter(language=PY_LANG)
    code = "def hello():\n    return 'world'\n"
    source_bytes = code.encode("utf-8")
    tree = splitter.parser.parse(source_bytes)
    ast_info = {"declarations": [{"name": "hello", "type": "function", "line": 1}], "imports": [], "references": []}

    wrapper = ParserWrapper(splitter.parser)
    splitter.parser = wrapper

    chunks = splitter.split_code(
        code,
        file_path="hello.py",
        tree=tree,
        source_bytes=source_bytes,
        ast_info=ast_info,
    )
    assert len(chunks) >= 1
    assert wrapper.call_count == 0


def test_smart_code_node_parser_uses_cached_ast_and_pops_internal_metadata():
    from kortext.ingest import Document
    from kortext.chunking.node_parser import SmartCodeNodeParser
    from kortext.chunking.languages import PY_LANG
    from kortext.chunking.ast_splitter import ASTCodeSplitter

    splitter = ASTCodeSplitter(language=PY_LANG)
    code = "def add(x, y):\n    return x + y\n"
    source_bytes = code.encode("utf-8")
    tree = splitter.parser.parse(source_bytes)
    ast_info = {"declarations": [{"name": "add", "type": "function", "line": 1}], "imports": [], "references": []}

    doc = Document(
        text=code,
        metadata={
            "file_path": "math_ops.py",
            "_tree": tree,
            "_source_bytes": source_bytes,
            "_ast_info": ast_info,
            "custom_meta": "keep_me",
        },
    )

    parser = SmartCodeNodeParser()
    nodes = parser.get_nodes_from_documents([doc])
    assert len(nodes) >= 1
    for n in nodes:
        assert "_tree" not in n.metadata
        assert "_source_bytes" not in n.metadata
        assert "_ast_info" not in n.metadata
        assert n.metadata.get("custom_meta") == "keep_me"


def test_ast_splitter_token_bounded_sizing_and_preamble():
    from kortext.chunking.ast_splitter import ASTCodeSplitter
    from kortext.chunking.languages import PY_LANG

    splitter = ASTCodeSplitter(language=PY_LANG)
    assert splitter.max_tokens == 384
    assert splitter.coalesce_target_tokens == 384
    assert splitter.overlap_tokens == 48

    code = (
        "class MetricsTracker:\n"
        "    \"\"\"Tracks throughput and latency for streaming workloads.\"\"\"\n"
        "    def __init__(self, buffer_size: int = 1024):\n"
        "        self.buffer_size = buffer_size\n"
        "        self.records = []\n\n"
        "    def record_metric(self, name: str, value: float) -> None:\n"
        "        \"\"\"Record a single numeric measurement.\"\"\"\n"
        "        self.records.append((name, value))\n"
    )
    chunks = splitter.split_text(code, file_path="metrics.py")
    assert len(chunks) >= 1

    first_chunk = chunks[0]
    # Check contextual preamble fields
    assert "# File: metrics.py" in first_chunk["text"]
    assert any("# Scope:" in c["text"] for c in chunks)
    assert any("# Signature:" in c["text"] for c in chunks)
    assert all(count_tokens(c["text"]) <= 384 + 100 for c in chunks)


def test_markdown_isolation_from_symbol_graph():
    from unittest.mock import MagicMock
    from kortext.symbols.graph import SymbolGraphManager
    from kortext.falkordb_client import FalkorDBClient

    mock_client = MagicMock(spec=FalkorDBClient)
    mock_client.query.return_value = [["res"], []]
    sgm = SymbolGraphManager(client=mock_client)

    sgm.save_markdown_ast(
        file_path="journal/2026-10-09.md",
        title="Daily Journal",
        frontmatter={"tags": ["journal"]},
        sections=[{"id": "journal/2026-10-09.md#summary", "name": "Summary", "level": 1, "line": 1, "heading_path": "Summary"}],
        declarations=[{"name": "Summary", "kind": "section", "line": 1, "signature": "# Summary", "docstring": "", "parent": ""}],
        links=[],
        tags=["journal"],
    )

    # Check queries executed
    queries = [call[0][1] for call in mock_client.query.call_args_list]
    # Ensure NO query created (s:Symbol) from markdown
    for q in queries:
        assert "(s:Symbol" not in q, f"Markdown heading leaked into Symbol node: {q}"
        assert ":Symbol {" not in q, f"Markdown heading leaked into Symbol node: {q}"


