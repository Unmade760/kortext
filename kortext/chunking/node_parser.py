"""
SmartCodeNodeParser: unified zero-dependency multi-format node parser for Kortext.

Dynamically routes:
- Source code (.py, .ts, .js, .rs, .go, .c, .cpp, .java, .kt, .swift, .cs) -> ASTCodeSplitter
- Markdown (.md, .markdown) -> MarkdownSectionSplitter
- Configuration (.yaml, .yml, .json, .toml) -> ConfigSectionSplitter
- Plain text -> SentenceSplitter
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Sequence
import uuid

from kortext.chunking.config_splitter import ConfigSectionSplitter
from kortext.chunking.languages import LANG_MAP
from kortext.chunking.markdown_splitter import MarkdownSectionSplitter


class NodeRelationship(str, Enum):
    """Lightweight relationship enum replacing llama_index.core.schema.NodeRelationship."""

    SOURCE = "1"
    PREVIOUS = "2"
    NEXT = "3"
    PARENT = "4"
    CHILD = "5"


@dataclass(frozen=True)
class RelatedNodeInfo:
    """Lightweight related node reference replacing llama_index.core.schema.RelatedNodeInfo."""

    node_id: str
    node_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    hash: Optional[str] = None


class BaseNode:
    """Lightweight zero-dependency base node replacing llama_index.core.schema.BaseNode."""

    def __init__(
        self,
        text: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        id_: Optional[str] = None,
        node_id: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        relationships: Optional[Dict[Any, Any]] = None,
        start_char_idx: Optional[int] = None,
        end_char_idx: Optional[int] = None,
        **kwargs: Any,
    ):
        self.text = text
        self.metadata: Dict[str, Any] = dict(metadata) if metadata else {}
        self.id_ = id_ or node_id or str(uuid.uuid4())
        self.embedding = embedding
        self.relationships: Dict[Any, Any] = dict(relationships) if relationships else {}
        self.start_char_idx = start_char_idx
        self.end_char_idx = end_char_idx
        self.excluded_embed_metadata_keys: List[str] = []
        self.excluded_llm_metadata_keys: List[str] = []

    @property
    def node_id(self) -> str:
        return self.id_

    @node_id.setter
    def node_id(self, value: str) -> None:
        self.id_ = value

    def get_content(self, *args: Any, **kwargs: Any) -> str:
        return self.text


class TextNode(BaseNode):
    """Lightweight zero-dependency TextNode replacing llama_index.core.schema.TextNode."""


class SentenceSplitter:
    """Lightweight paragraph and sentence window splitter replacing LlamaIndex SentenceSplitter."""

    def __init__(self, chunk_size: int = 1536, chunk_overlap: int = 192, **kwargs: Any):
        self.chunk_size = max(128, int(chunk_size))
        self.chunk_overlap = max(0, min(int(chunk_overlap), self.chunk_size // 2))

    def split_text(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []
        max_chars = self.chunk_size * 4
        overlap_chars = self.chunk_overlap * 4
        if len(text) <= max_chars:
            return [text]

        units = [u for u in re.split(r"(?<=[.!?])\s+|\n\n+", text) if u]
        chunks: List[str] = []
        current: List[str] = []
        curr_len = 0

        for unit in units:
            u_len = len(unit)
            if u_len > max_chars:
                if current:
                    chunks.append(" ".join(current))
                    current = []
                    curr_len = 0
                step = max(1, max_chars - overlap_chars)
                for idx in range(0, u_len, step):
                    chunks.append(unit[idx : idx + max_chars])
                continue

            if curr_len + u_len + 1 > max_chars and current:
                chunks.append(" ".join(current))
                # Retain overlap tail
                tail: List[str] = []
                tail_len = 0
                for prev_u in reversed(current):
                    if tail_len + len(prev_u) <= overlap_chars:
                        tail.insert(0, prev_u)
                        tail_len += len(prev_u) + 1
                    else:
                        break
                current = tail
                curr_len = tail_len

            current.append(unit)
            curr_len += u_len + 1

        if current:
            chunks.append(" ".join(current))
        return chunks

    def get_nodes_from_documents(self, documents: Sequence[Any], **kwargs: Any) -> List[TextNode]:
        nodes: List[TextNode] = []
        for doc in documents:
            text = doc.get_content() if hasattr(doc, "get_content") else getattr(doc, "text", "")
            meta = dict(getattr(doc, "metadata", {}) or {})
            doc_id = getattr(doc, "node_id", getattr(doc, "id_", str(uuid.uuid4())))
            for chunk_str in self.split_text(text):
                tn = TextNode(text=chunk_str, metadata=dict(meta))
                tn.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=doc_id)
                nodes.append(tn)
        return nodes


class NodeParser:
    """Base node parser interface replacing llama_index.core.node_parser.NodeParser."""

    def __init__(self, chunk_size: int = 1536, chunk_overlap: int = 192, **kwargs: Any):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _parse_nodes(self, nodes: Sequence[BaseNode], show_progress: bool = False, **kwargs: Any) -> List[BaseNode]:
        return list(nodes)

    def _postprocess_parsed_nodes(self, nodes: List[BaseNode], parent_doc_map: Any = None) -> List[BaseNode]:
        return nodes

    def get_nodes_from_documents(
        self,
        documents: Sequence[Any],
        show_progress: bool = False,
        **kwargs: Any,
    ) -> List[BaseNode]:
        parsed = self._parse_nodes(documents, show_progress=show_progress, **kwargs)
        return self._postprocess_parsed_nodes(parsed, None)


class SmartCodeNodeParser(NodeParser):
    """
    State-of-the-Art Intelligent NodeParser for Kortext.
    Dynamically routes files to specialized splitters:
    - Code (.py, .ts, .js, .jsx, .tsx, .rs, .go, .c, .cpp, etc.) -> ASTCodeSplitter
    - Markdown (.md) -> MarkdownSectionSplitter
    - Configs (.yaml, .yml, .json, .toml) -> ConfigSectionSplitter
    - Plain text / Fallbacks -> SentenceSplitter with file breadcrumbs
    """

    chunk_size: int = 1536
    chunk_overlap: int = 192
    max_tokens: int = 384
    overlap_tokens: int = 48

    def __init__(
        self,
        chunk_size: int = 1536,
        chunk_overlap: int = 192,
        max_tokens: int = 384,
        overlap_tokens: int = 48,
        **kwargs: Any,
    ):
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap, **kwargs)
        if chunk_size != 1536 and max_tokens == 384:
            self.max_tokens = max(128, chunk_size // 4)
        else:
            self.max_tokens = max_tokens

        if chunk_overlap != 192 and overlap_tokens == 48:
            self.overlap_tokens = max(16, chunk_overlap // 4)
        else:
            self.overlap_tokens = overlap_tokens

        self._sentence_splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self._md_splitter = MarkdownSectionSplitter(max_tokens=self.max_tokens)
        self._config_splitter = ConfigSectionSplitter(max_tokens=self.max_tokens)
        self._ast_splitters: Dict[Any, Any] = {}

    def _get_ast_splitter(self, lang: Any) -> Any:
        splitter = self._ast_splitters.get(lang)
        if splitter is None:
            from kortext.chunking.ast_splitter import ASTCodeSplitter

            splitter = ASTCodeSplitter(
                language=lang,
                max_tokens=self.max_tokens,
                overlap_tokens=self.overlap_tokens,
            )
            self._ast_splitters[lang] = splitter
        return splitter

    def _parse_nodes(
        self,
        nodes: Sequence[BaseNode],
        show_progress: bool = False,
        **kwargs: Any,
    ) -> List[BaseNode]:
        from kortext.chunking.ast_splitter import get_file_temporal_info

        all_nodes: List[BaseNode] = []

        include_verbose = os.getenv("KORTEXT_VERBOSE_PREAMBLE", "0") == "1"
        for node in nodes:
            file_path = node.metadata.get("file_path", "")
            ext = Path(file_path).suffix.lower() if file_path else ""
            text = node.get_content()
            file_temporal = get_file_temporal_info(file_path) if (file_path and include_verbose) else None

            # Strategy 1: AST Code Splitter (Code files)
            if ext in LANG_MAP:
                lang = LANG_MAP[ext]
                splitter = self._get_ast_splitter(lang)
                tree = node.metadata.get("_tree")
                source_bytes = node.metadata.get("_source_bytes")
                ast_info = node.metadata.get("_ast_info")
                raw_chunks = splitter.split_code(
                    text,
                    file_path=file_path,
                    tree=tree,
                    source_bytes=source_bytes,
                    ast_info=ast_info,
                )

                node.metadata.pop("_tree", None)
                node.metadata.pop("_source_bytes", None)
                node.metadata.pop("_ast_info", None)

                for chunk in raw_chunks:
                    meta = dict(node.metadata)
                    meta.pop("_tree", None)
                    meta.pop("_source_bytes", None)
                    meta.pop("_ast_info", None)
                    meta["scope"] = chunk.get("scope", "")
                    meta["chunk_type"] = chunk.get("chunk_type", "ast_code")
                    if "dependencies" in chunk:
                        meta["dependencies"] = chunk["dependencies"]
                    if "parent_id" in chunk:
                        meta["parent_id"] = chunk["parent_id"]
                        meta["parent_scope"] = chunk.get("parent_scope", "")
                        meta["parent_text"] = chunk.get("parent_text", "")
                    if "test_targets" in chunk:
                        meta["test_targets"] = chunk["test_targets"]
                    if "docstring" in chunk:
                        meta["docstring"] = chunk["docstring"]
                    if "signature" in chunk:
                        meta["signature"] = chunk["signature"]
                    if "commit_hash" in chunk:
                        meta["commit_hash"] = chunk["commit_hash"]
                        meta["commit_date"] = chunk.get("commit_date", "")
                        meta["commit_msg"] = chunk.get("commit_msg", "")
                    text_node = TextNode(
                        text=chunk["text"],
                        metadata=meta,
                        start_char_idx=chunk.get("start_char", 0),
                        end_char_idx=chunk.get("end_char", len(chunk["text"])),
                    )
                    text_node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=node.node_id)
                    all_nodes.append(text_node)

            # Strategy 2: Markdown Section Splitter
            elif ext in (".md", ".markdown"):
                raw_chunks = self._md_splitter.split_markdown(text, file_path=file_path)
                for chunk in raw_chunks:
                    meta = dict(node.metadata)
                    meta["scope"] = chunk.get("scope", "")
                    meta["parent_scope"] = chunk.get("parent_scope", "")
                    meta["parent_symbol"] = chunk.get("heading_path", "")
                    meta["heading_path"] = chunk.get("heading_path", "")
                    meta["chunk_type"] = chunk.get("chunk_type", "markdown_section")
                    if chunk.get("tags"):
                        meta["tags"] = chunk["tags"]
                    if file_temporal:
                        meta["commit_hash"] = file_temporal["commit_hash"]
                        meta["commit_date"] = file_temporal["commit_date"]
                        meta["commit_msg"] = file_temporal["commit_msg"]
                    text_node = TextNode(
                        text=chunk["text"],
                        metadata=meta,
                        start_char_idx=chunk.get("start_char", 0),
                        end_char_idx=chunk.get("end_char", len(chunk["text"])),
                    )
                    text_node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=node.node_id)
                    all_nodes.append(text_node)

            # Strategy 3: Structured Config Splitter (.json, .yaml, .yml, .toml)
            elif ext in (".json", ".yaml", ".yml", ".toml"):
                raw_chunks = self._config_splitter.split_config(text, file_path=file_path)
                for chunk in raw_chunks:
                    meta = dict(node.metadata)
                    meta["scope"] = chunk.get("scope", "")
                    meta["chunk_type"] = chunk.get("chunk_type", "config_section")
                    if file_temporal:
                        meta["commit_hash"] = file_temporal["commit_hash"]
                        meta["commit_date"] = file_temporal["commit_date"]
                        meta["commit_msg"] = file_temporal["commit_msg"]
                    text_node = TextNode(
                        text=chunk["text"],
                        metadata=meta,
                        start_char_idx=chunk.get("start_char", 0),
                        end_char_idx=chunk.get("end_char", len(chunk["text"])),
                    )
                    text_node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=node.node_id)
                    all_nodes.append(text_node)

            # Strategy 4: Fallback Plain Text Sentence Splitter
            else:
                sub_nodes = self._sentence_splitter.get_nodes_from_documents([node])
                for sn in sub_nodes:
                    meta = dict(sn.metadata)
                    meta["chunk_type"] = "text_sentence"
                    if file_temporal:
                        meta["commit_hash"] = file_temporal["commit_hash"]
                        meta["commit_date"] = file_temporal["commit_date"]
                        meta["commit_msg"] = file_temporal["commit_msg"]
                    breadcrumb = f"# File: {file_path}\n\n" if file_path else ""
                    sn.text = breadcrumb + sn.text
                    sn.metadata = meta
                    all_nodes.append(sn)

        return all_nodes

    def _postprocess_parsed_nodes(
        self, nodes: List[BaseNode], parent_doc_map: Any = None
    ) -> List[BaseNode]:
        nodes = super()._postprocess_parsed_nodes(nodes, parent_doc_map)
        for n in nodes:
            n.metadata.pop("_tree", None)
            n.metadata.pop("_source_bytes", None)
            n.metadata.pop("_ast_info", None)
        return nodes
