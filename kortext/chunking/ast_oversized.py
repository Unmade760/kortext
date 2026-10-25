"""Oversized AST function and statement sub-splitting mixin."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from kortext.chunking.token_utils import count_tokens

try:
    from tree_sitter import Node as TSNode
except Exception:
    TSNode = Any  # type: ignore

logger = logging.getLogger(__name__)


class ASTOversizedSplitterMixin:
    """Mixin providing statement-level and token-overlap sub-splitting for oversized AST nodes."""

    def _split_oversized_function(
        self,
        node: TSNode,
        actual_fn: TSNode,
        scope: str,
        signature: str,
        fn_doc: Optional[str],
        source_bytes: bytes,
        file_path: str,
        module_summary: Optional[str],
        import_map: Optional[Dict[str, str]] = None,
        ast_info: Optional[Dict[str, Any]] = None,
        temporal_info: Optional[Dict[str, str]] = None,
        parent_id: Optional[str] = None,
        parent_scope: Optional[str] = None,
        parent_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Splits a large function along AST statement boundaries with sliding-window overlap.
        Preserves complete control flow (try/except, loops, conditions) and parent hierarchy.
        """
        import_map = import_map or {}
        ast_info = ast_info or {}
        if parent_id is None:
            stripped_scope = re.sub(r"^(?:async\s+def|def|fn|func)\s+", "", scope.strip())
            clean_scope = re.sub(r"[^A-Za-z0-9_]+", "_", stripped_scope).strip("_")
            parent_id = f"{file_path}::{clean_scope}"
            parent_scope = scope
            parent_text = f"{signature}\n{fn_doc or ''}"[:2000]

        decls = ast_info.get("declarations", [])
        _get_deps = lambda txt: self._resolve_deps(txt, import_map)
        _get_test_targets = lambda idn, txt: self._resolve_test_targets(idn, txt, file_path, import_map, decls)

        body_node = self._get_body_node(actual_fn)
        if not body_node or not body_node.children:
            full_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            header = self._make_context_preamble(
                file_path, module_summary, scope, signature, docstring=fn_doc, temporal_info=temporal_info
            )
            sub_chunks = self._subsplit_text_with_overlap(full_text, header, scope, node.start_byte)
            for sc in sub_chunks:
                sc["parent_id"] = parent_id
                sc["parent_scope"] = parent_scope
                sc["parent_text"] = parent_text
                sc["commit_hash"] = temporal_info["commit_hash"] if temporal_info else "local"
                sc["commit_date"] = temporal_info["commit_date"] if temporal_info else ""
                sc["commit_msg"] = temporal_info["commit_msg"] if temporal_info else ""
            return sub_chunks

        # Filter meaningful statements (ignore braces, colons, docstrings if already extracted)
        statements: List[TSNode] = []
        for child in body_node.children:
            if child.type in (":", "{", "}"):
                continue
            statements.append(child)

        if not statements:
            full_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            header = self._make_context_preamble(
                file_path, module_summary, scope, signature, docstring=fn_doc, temporal_info=temporal_info
            )
            sub_chunks = self._subsplit_text_with_overlap(full_text, header, scope, node.start_byte)
            for sc in sub_chunks:
                sc["parent_id"] = parent_id
                sc["parent_scope"] = parent_scope
                sc["parent_text"] = parent_text
                sc["commit_hash"] = temporal_info["commit_hash"] if temporal_info else "local"
                sc["commit_date"] = temporal_info["commit_date"] if temporal_info else ""
                sc["commit_msg"] = temporal_info["commit_msg"] if temporal_info else ""
            return sub_chunks

        chunks: List[Dict[str, Any]] = []
        curr_stmts: List[TSNode] = []
        curr_tokens = 0
        part_idx = 1

        for stmt in statements:
            stmt_text = source_bytes[stmt.start_byte:stmt.end_byte].decode("utf-8", errors="replace")
            stmt_toks = count_tokens(stmt_text)

            # If a single statement exceeds max_tokens, sub-split it with text overlap
            if stmt_toks > self.max_tokens:
                if curr_stmts:
                    c_text = source_bytes[curr_stmts[0].start_byte:curr_stmts[-1].end_byte].decode("utf-8", errors="replace")
                    c_deps = _get_deps(c_text)
                    c_targets = _get_test_targets(scope, c_text)
                    chunks.append(self._build_statement_chunk(
                        curr_stmts, source_bytes, file_path, module_summary, scope, signature, part_idx,
                        docstring=fn_doc, dependencies=c_deps, test_targets=c_targets, temporal_info=temporal_info,
                        parent_id=parent_id, parent_scope=parent_scope, parent_text=parent_text,
                    ))
                    part_idx += 1
                    curr_stmts = []
                    curr_tokens = 0

                s_deps = _get_deps(stmt_text)
                s_targets = _get_test_targets(scope, stmt_text)
                sub_hdr = self._make_context_preamble(
                    file_path, module_summary, scope, signature, part_info=f"Part {part_idx} (large statement)",
                    docstring=fn_doc, dependencies=s_deps, test_targets=s_targets, temporal_info=temporal_info,
                )
                stmt_chunks = self._subsplit_text_with_overlap(stmt_text, sub_hdr, scope, stmt.start_byte)
                for sc in stmt_chunks:
                    sc["parent_id"] = parent_id
                    sc["parent_scope"] = parent_scope
                    sc["parent_text"] = parent_text
                    sc["dependencies"] = s_deps
                    sc["test_targets"] = s_targets
                    sc["commit_hash"] = temporal_info["commit_hash"] if temporal_info else "local"
                    sc["commit_date"] = temporal_info["commit_date"] if temporal_info else ""
                    sc["commit_msg"] = temporal_info["commit_msg"] if temporal_info else ""
                chunks.extend(stmt_chunks)
                part_idx += len(stmt_chunks)
                continue

            if curr_tokens + stmt_toks > self.max_tokens and curr_stmts:
                c_text = source_bytes[curr_stmts[0].start_byte:curr_stmts[-1].end_byte].decode("utf-8", errors="replace")
                c_deps = _get_deps(c_text)
                c_targets = _get_test_targets(scope, c_text)
                chunks.append(self._build_statement_chunk(
                    curr_stmts, source_bytes, file_path, module_summary, scope, signature, part_idx,
                    docstring=fn_doc, dependencies=c_deps, test_targets=c_targets, temporal_info=temporal_info,
                    parent_id=parent_id, parent_scope=parent_scope, parent_text=parent_text,
                ))
                part_idx += 1

                # Calculate AST sliding-window overlap: retain last N statements <= overlap_tokens
                overlap_stmts: List[TSNode] = []
                overlap_accum = 0
                for prev in reversed(curr_stmts):
                    prev_text = source_bytes[prev.start_byte:prev.end_byte].decode("utf-8", errors="replace")
                    prev_toks = count_tokens(prev_text)
                    if overlap_accum + prev_toks <= self.overlap_tokens:
                        overlap_stmts.insert(0, prev)
                        overlap_accum += prev_toks
                    else:
                        break

                curr_stmts = list(overlap_stmts)
                curr_tokens = overlap_accum

            curr_stmts.append(stmt)
            curr_tokens += stmt_toks

        if curr_stmts:
            c_text = source_bytes[curr_stmts[0].start_byte:curr_stmts[-1].end_byte].decode("utf-8", errors="replace")
            c_deps = _get_deps(c_text)
            c_targets = _get_test_targets(scope, c_text)
            chunks.append(self._build_statement_chunk(
                curr_stmts, source_bytes, file_path, module_summary, scope, signature, part_idx,
                docstring=fn_doc, dependencies=c_deps, test_targets=c_targets, temporal_info=temporal_info,
                parent_id=parent_id, parent_scope=parent_scope, parent_text=parent_text,
            ))

        return chunks

    def _build_statement_chunk(
        self,
        stmts: List[TSNode],
        source_bytes: bytes,
        file_path: str,
        module_summary: Optional[str],
        scope: str,
        signature: str,
        part_idx: int,
        docstring: Optional[str] = None,
        dependencies: Optional[List[Dict[str, str]]] = None,
        test_targets: Optional[List[str]] = None,
        temporal_info: Optional[Dict[str, str]] = None,
        parent_id: Optional[str] = None,
        parent_scope: Optional[str] = None,
        parent_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_b = stmts[0].start_byte
        end_b = stmts[-1].end_byte
        body_text = source_bytes[start_b:end_b].decode("utf-8", errors="replace").strip()
        part_info = f"Part {part_idx}" if part_idx > 1 else None
        header = self._make_context_preamble(
            file_path=file_path,
            module_summary=module_summary,
            scope=scope,
            signature=signature,
            part_info=part_info,
            docstring=docstring,
            dependencies=dependencies,
            test_targets=test_targets,
            temporal_info=temporal_info,
        )
        return {
            "text": header + body_text,
            "scope": f"{scope} ({part_info or 'full'})",
            "chunk_type": "ast_code",
            "start_char": start_b,
            "end_char": end_b,
            "signature": signature,
            "docstring": docstring or "",
            "dependencies": dependencies or [],
            "test_targets": test_targets or [],
            "parent_id": parent_id,
            "parent_scope": parent_scope,
            "parent_text": parent_text,
            "commit_hash": temporal_info["commit_hash"] if temporal_info else "local",
            "commit_date": temporal_info["commit_date"] if temporal_info else "",
            "commit_msg": temporal_info["commit_msg"] if temporal_info else "",
        }

    def _subsplit_text_with_overlap(
        self,
        text: str,
        header: str,
        scope: str,
        base_offset: int,
    ) -> List[Dict[str, Any]]:
        """Fallback line-based sub-splitter with token overlap."""
        lines = text.splitlines(keepends=True)
        chunks = []
        curr_lines = []
        curr_tokens = count_tokens(header)
        curr_start = base_offset

        for line in lines:
            line_toks = count_tokens(line)
            if curr_tokens + line_toks > self.max_tokens and curr_lines:
                chunk_body = "".join(curr_lines).strip()
                chunks.append({
                    "text": header + chunk_body,
                    "scope": scope,
                    "chunk_type": "ast_code",
                    "start_char": curr_start,
                    "end_char": curr_start + len(chunk_body),
                })
                # Overlap last ~15% lines
                prev_non_overlap_chars = (
                    sum(len(l) for l in curr_lines[:-3])
                    if len(curr_lines) > 3
                    else sum(len(l) for l in curr_lines)
                )
                overlap_lines = curr_lines[-3:] if len(curr_lines) >= 3 else []
                curr_lines = list(overlap_lines)
                curr_tokens = count_tokens(header) + sum(count_tokens(l) for l in curr_lines)
                curr_start += prev_non_overlap_chars

            curr_lines.append(line)
            curr_tokens += line_toks

        if curr_lines:
            chunk_body = "".join(curr_lines).strip()
            chunks.append({
                "text": header + chunk_body,
                "scope": scope,
                "chunk_type": "ast_code",
                "start_char": curr_start,
                "end_char": curr_start + len(chunk_body),
            })

        return chunks
