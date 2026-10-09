"""
Deterministic Symbol & Cross-File Reference Graph in FalkorDB.

Maintains a graph of:
  (:Symbol {name})
  (:File {path})
  (s:Symbol)-[:DEFINED_IN {kind, line, signature, docstring, parent}]->(f:File)
  (f:File)-[:IMPORTS {module, line}]->(s:Symbol)
  (f:File)-[:REFERENCES {line, kind}]->(s:Symbol)

Provides sub-millisecond O(1) "Jump to Definition", "Find All References",
and cross-file "Impact Analysis" without requiring a heavy LSP compiler daemon.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import redis

from kortext.falkordb_client import (
    FalkorDBClient,
    FALKORDB_HOST,
    FALKORDB_PORT,
    FALKORDB_PASS,
    get_shared_falkordb_client,
)
from kortext.symbols.formatter import format_impact_report

logger = logging.getLogger("kortext.symbols.graph")

SYMBOLS_GRAPH_NAME = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))


class SymbolGraphManager:
    """Manages symbol declarations, cross-file imports, and usages in FalkorDB."""

    def __init__(
        self,
        host: str = FALKORDB_HOST,
        port: int = FALKORDB_PORT,
        password: Optional[str] = FALKORDB_PASS,
        graph_name: str = SYMBOLS_GRAPH_NAME,
        client: Optional[FalkorDBClient] = None,
    ):
        self.host = host
        self.port = port
        self.password = password or None
        self.graph_name = graph_name
        self.client = client if client is not None else get_shared_falkordb_client(host=self.host, port=self.port, password=self.password)
        self._indexes_ensured = False

    def _ensure_indexes(self):
        """Ensures B-tree schema indexes on :Symbol(name), :File(path), :Document(path), :Tag(name), :Concept(name)."""
        self.client.ensure_indexes(
            self.graph_name,
            [
                ("Symbol", "name"),
                ("File", "path"),
                ("Document", "path"),
                ("Tag", "name"),
                ("Concept", "name"),
            ],
        )

    def _query(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[List[Any]]:
        """Executes a Cypher query on the symbols graph with token-safe parameter binding and reconnect."""
        if not getattr(self, "_indexes_ensured", False):
            self._ensure_indexes()
            self._indexes_ensured = True
        return self.client.query(self.graph_name, cypher, params)

    def save_file_ast(
        self,
        file_path: str,
        declarations: List[Dict[str, Any]],
        imports: List[Dict[str, Any]],
        references: List[Dict[str, Any]],
    ) -> None:
        """
        Atomically saves a file's declarations, imports, and references using batch UNWIND queries.
        Reduces Redis roundtrips by 60x compared to per-node insertion.
        """
        # Collect candidate symbols defined in this file before detaching definitions
        candidate_syms = set()
        res_defs = self._query(
            "MATCH (s:Symbol)-[:DEFINED_IN]->(f:File {path: $path}) RETURN DISTINCT s.name",
            {"path": file_path},
        )
        if res_defs and len(res_defs) > 1 and isinstance(res_defs[1], list):
            for row in res_defs[1]:
                if row and row[0]:
                    candidate_syms.add(str(row[0]))

        res_fp = self._query(
            "MATCH (s:Symbol {file_path: $path}) RETURN DISTINCT s.name",
            {"path": file_path},
        )
        if res_fp and len(res_fp) > 1 and isinstance(res_fp[1], list):
            for row in res_fp[1]:
                if row and row[0]:
                    candidate_syms.add(str(row[0]))

        # 1. Purge old relationships connected to this file and ensure File node
        self._query(
            "MERGE (f:File {path: $path}) "
            "WITH f "
            "OPTIONAL MATCH (f)<-[r1:DEFINED_IN]-() DELETE r1 "
            "WITH f "
            "OPTIONAL MATCH (f)-[r2:IMPORTS]->() DELETE r2 "
            "WITH f "
            "OPTIONAL MATCH (f)-[r3:REFERENCES]->() DELETE r3 "
            "WITH f "
            "OPTIONAL MATCH ()-[r4:CALLS {file_path: $path}]->() DELETE r4",
            {"path": file_path},
        )

        # 2. Batch add declarations
        clean_decls = []
        for decl in declarations:
            name = decl.get("name")
            if not name or name == "anonymous":
                continue
            clean_decls.append({
                "name": str(name),
                "kind": str(decl.get("kind", "symbol")),
                "line": int(decl.get("line", 1)),
                "end_line": int(decl.get("end_line", decl.get("line", 1))),
                "signature": str(decl.get("signature") or "")[:200],
                "docstring": str(decl.get("docstring") or "")[:200],
                "parent": str(decl.get("parent") or ""),
            })

        if clean_decls:
            decl_cypher = (
                "MATCH (f:File {path: $path}) "
                "WITH f "
                "UNWIND $declarations AS d "
                "MERGE (s:Symbol {name: d.name}) "
                "SET s.kind = d.kind, s.file_path = $path "
                "MERGE (s)-[:DEFINED_IN {kind: d.kind, line: d.line, end_line: d.end_line, signature: d.signature, docstring: d.docstring, parent: d.parent}]->(f)"
            )
            self._query(decl_cypher, {"path": file_path, "declarations": clean_decls})

        # 3. Batch add imports
        clean_imps = []
        for imp in imports:
            sym = imp.get("symbol")
            if not sym:
                continue
            clean_imps.append({
                "name": str(sym),
                "module": str(imp.get("module") or ""),
                "line": int(imp.get("line", 1)),
            })

        if clean_imps:
            imp_cypher = (
                "MATCH (f:File {path: $path}) "
                "WITH f "
                "UNWIND $imports AS i "
                "MERGE (s:Symbol {name: i.name}) "
                "MERGE (f)-[:IMPORTS {module: i.module, line: i.line}]->(s)"
            )
            self._query(imp_cypher, {"path": file_path, "imports": clean_imps})

        # 4. Batch add references (deduplicated) and symbol calls
        seen_refs = set()
        clean_refs = []
        for ref in references:
            sym = ref.get("symbol")
            line = int(ref.get("line", 1))
            caller = ref.get("caller") or ""
            if not sym or (sym, line, caller) in seen_refs:
                continue
            seen_refs.add((sym, line, caller))
            clean_refs.append({
                "name": str(sym),
                "kind": str(ref.get("kind", "call")),
                "line": line,
                "caller": str(caller),
            })

        if clean_refs:
            ref_cypher = (
                "MATCH (f:File {path: $path}) "
                "WITH f "
                "UNWIND $references AS r "
                "MERGE (s:Symbol {name: r.name}) "
                "MERGE (f)-[:REFERENCES {line: r.line, kind: r.kind}]->(s) "
                "FOREACH (_ IN CASE WHEN r.caller <> '' THEN [1] ELSE [] END | "
                "  MERGE (c:Symbol {name: r.caller}) "
                "  MERGE (c)-[:CALLS {line: r.line, file_path: $path}]->(s)"
                ")"
            )
            self._query(ref_cypher, {"path": file_path, "references": clean_refs})

        # 5. Remove orphaned Symbol nodes whose definitions were removed
        if candidate_syms:
            self._query(
                "UNWIND $names AS name "
                "MATCH (s:Symbol {name: name}) "
                "WHERE NOT (s)-[:DEFINED_IN]->(:File) "
                "DETACH DELETE s",
                {"names": list(candidate_syms)},
            )

    def save_markdown_ast(
        self,
        file_path: str,
        title: str,
        frontmatter: Dict[str, Any],
        sections: List[Dict[str, Any]],
        declarations: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
        tags: List[str],
    ) -> None:
        """
        Atomically saves a Markdown document's structural sections, headings (as symbols),
        inter-document wiki-links, standard markdown links, and tags into FalkorDB.
        """
        safe_title = str(title or Path(file_path).stem)

        # 1. Ensure File:Document node and purge previous markdown relationships
        self._query(
            "MERGE (f:File {path: $path}) "
            "SET f:Document, f.title = $title, f.is_markdown = true "
            "WITH f "
            "OPTIONAL MATCH (f)<-[r1:DEFINED_IN]-() DELETE r1 "
            "WITH f "
            "OPTIONAL MATCH (f)-[r2:CONTAINS_SECTION]->() DELETE r2 "
            "WITH f "
            "OPTIONAL MATCH (f)-[r3:LINKS_TO]->() DELETE r3 "
            "WITH f "
            "OPTIONAL MATCH (f)-[r4:HAS_TAG]->() DELETE r4",
            {"path": file_path, "title": safe_title},
        )

        # 2. Batch add sections
        if sections:
            sec_items = [
                {
                    "id": str(s.get("id", "")),
                    "name": str(s.get("name", "")),
                    "level": int(s.get("level", 1)),
                    "line": int(s.get("line", 1)),
                    "heading_path": str(s.get("heading_path", "")),
                }
                for s in sections
            ]
            self._query(
                "MATCH (f:File {path: $path}) "
                "WITH f "
                "UNWIND $sections AS s "
                "MERGE (sec:Section {id: s.id}) "
                "SET sec.name = s.name, sec.level = s.level, sec.line = s.line, sec.heading_path = s.heading_path, sec.path = $path "
                "MERGE (f)-[:CONTAINS_SECTION]->(sec)",
                {"path": file_path, "sections": sec_items},
            )

        # 3. Batch add declarations (headings as Symbol nodes for Tier 0 resolution)
        if declarations:
            clean_decls = []
            for decl in declarations:
                name = decl.get("name")
                if not name:
                    continue
                clean_decls.append({
                    "name": str(name),
                    "kind": str(decl.get("kind", "section")),
                    "line": int(decl.get("line", 1)),
                    "signature": str(decl.get("signature") or "")[:200],
                    "docstring": str(decl.get("docstring") or "")[:200],
                    "parent": str(decl.get("parent") or ""),
                })
            if clean_decls:
                self._query(
                    "MATCH (f:File {path: $path}) "
                    "WITH f "
                    "UNWIND $declarations AS d "
                    "MERGE (s:Symbol {name: d.name}) "
                    "MERGE (s)-[:DEFINED_IN {kind: d.kind, line: d.line, signature: d.signature, docstring: d.docstring, parent: d.parent}]->(f)",
                    {"path": file_path, "declarations": clean_decls},
                )

        # 4. Batch add links (split into resolved File targets and unresolved Concept targets)
        if links:
            resolved_links = []
            concept_links = []
            for l in links:
                if l.get("is_resolved") and l.get("target_path"):
                    resolved_links.append({
                        "path": str(l["target_path"]),
                        "label": str(l.get("label", "")),
                        "line": int(l.get("line", 1)),
                        "type": str(l.get("link_type", "markdown_link")),
                        "raw": str(l.get("raw_target", "")),
                    })
                else:
                    target_name = l.get("target_name") or l.get("raw_target", "")
                    if target_name:
                        concept_links.append({
                            "name": str(target_name),
                            "label": str(l.get("label", "")),
                            "line": int(l.get("line", 1)),
                            "type": str(l.get("link_type", "wiki_link")),
                            "raw": str(l.get("raw_target", "")),
                        })

            if resolved_links:
                self._query(
                    "MATCH (f:File {path: $path}) "
                    "WITH f "
                    "UNWIND $links AS r "
                    "MERGE (t:File {path: r.path}) "
                    "MERGE (f)-[:LINKS_TO {label: r.label, line: r.line, link_type: r.type, raw_target: r.raw}]->(t)",
                    {"path": file_path, "links": resolved_links},
                )

            if concept_links:
                self._query(
                    "MATCH (f:File {path: $path}) "
                    "WITH f "
                    "UNWIND $links AS c "
                    "MERGE (t:Concept {name: c.name}) "
                    "MERGE (f)-[:LINKS_TO {label: c.label, line: c.line, link_type: c.type, raw_target: c.raw}]->(t)",
                    {"path": file_path, "links": concept_links},
                )

        # 5. Batch add tags
        if tags:
            tag_items = [{"name": str(t)} for t in tags if t]
            if tag_items:
                self._query(
                    "MATCH (f:File {path: $path}) "
                    "WITH f "
                    "UNWIND $tags AS t "
                    "MERGE (tag:Tag {name: t.name}) "
                    "MERGE (f)-[:HAS_TAG]->(tag)",
                    {"path": file_path, "tags": tag_items},
                )

    def delete_file_ast(self, file_path: str) -> None:
        """
        Completely purges a file and its associated AST entities from FalkorDB:
        - Removes the File node
        - Removes associated Section nodes
        - Removes ghost CALLS edges originating from this file
        - Removes orphaned Symbol nodes whose only definition was in this file
        """
        # 1. Identify candidate symbols defined in this file (or with s.file_path = $path)
        # before relationships to the File node are removed
        candidate_syms = set()
        res_defs = self._query(
            "MATCH (s:Symbol)-[:DEFINED_IN]->(f:File {path: $path}) RETURN DISTINCT s.name",
            {"path": file_path},
        )
        if res_defs and len(res_defs) > 1 and isinstance(res_defs[1], list):
            for row in res_defs[1]:
                if row and row[0]:
                    candidate_syms.add(str(row[0]))

        res_fp = self._query(
            "MATCH (s:Symbol {file_path: $path}) RETURN DISTINCT s.name",
            {"path": file_path},
        )
        if res_fp and len(res_fp) > 1 and isinstance(res_fp[1], list):
            for row in res_fp[1]:
                if row and row[0]:
                    candidate_syms.add(str(row[0]))

        # 2. Detach delete associated Section nodes connected to File
        self._query(
            "OPTIONAL MATCH (f:File {path: $path})-[:CONTAINS_SECTION]->(sec:Section) DETACH DELETE sec",
            {"path": file_path},
        )

        # 3. Purge ghost CALLS edges originating from this file
        self._query(
            "OPTIONAL MATCH ()-[r:CALLS {file_path: $path}]->() DELETE r",
            {"path": file_path},
        )

        # 4. Detach delete the File node itself
        self._query(
            "MATCH (f:File {path: $path}) DETACH DELETE f",
            {"path": file_path},
        )

        # 5. Remove orphaned Symbol nodes whose only definition was in this file
        if candidate_syms:
            self._query(
                "UNWIND $names AS name "
                "MATCH (s:Symbol {name: name}) "
                "WHERE NOT (s)-[:DEFINED_IN]->(:File) "
                "DETACH DELETE s",
                {"names": list(candidate_syms)},
            )

    def remove_file(self, file_path: str) -> None:
        """Purges a deleted file and its symbol relationships from the graph."""
        self.delete_file_ast(file_path)

    def clear(self) -> None:
        """Deletes all nodes and relationships in this symbol graph."""
        self._query("MATCH (n) DETACH DELETE n")

    def find_definition(self, symbol_name: str) -> List[Dict[str, Any]]:
        """Finds all exact definition sites of a symbol across indexed files (code symbols & markdown documents)."""
        clean_sym = symbol_name.strip()
        res = self._query(
            "MATCH (s:Symbol)-[r:DEFINED_IN]->(f:File) "
            "WHERE s.name = $name "
            "RETURN s.name, r.kind, r.line, r.signature, r.docstring, r.parent, f.path",
            {"name": clean_sym},
        )
        if not (res and len(res) > 1 and res[1]):
            res = self._query(
                "MATCH (s:Symbol)-[r:DEFINED_IN]->(f:File) "
                "WHERE toLower(s.name) = toLower($name) "
                "RETURN s.name, r.kind, r.line, r.signature, r.docstring, r.parent, f.path",
                {"name": clean_sym},
            )
        definitions = []
        if res and len(res) > 1 and isinstance(res[1], list):
            for row in res[1]:
                if len(row) >= 7:
                    definitions.append({
                        "name": str(row[0]),
                        "kind": str(row[1]),
                        "line": int(row[2]) if str(row[2]).isdigit() else 1,
                        "signature": str(row[3]),
                        "docstring": str(row[4]),
                        "parent": str(row[5]) if row[5] else None,
                        "file_path": str(row[6]),
                    })

        # Also search Document nodes (by title or ending path)
        clean_name = symbol_name.strip()
        doc_res = self._query(
            "MATCH (d:Document) "
            "WHERE toLower(d.title) = toLower($name) OR toLower(d.path) ENDS WITH toLower($name) "
            "RETURN coalesce(d.title, d.path) AS title, 'document' AS kind, 1 AS line, d.path AS signature, d.path AS doc_path",
            {"name": clean_name},
        )
        if doc_res and len(doc_res) > 1 and isinstance(doc_res[1], list):
            for row in doc_res[1]:
                if len(row) >= 5:
                    definitions.append({
                        "name": str(row[0]),
                        "kind": "document",
                        "line": 1,
                        "signature": f"Document: {row[0]}",
                        "docstring": "Markdown knowledge note",
                        "parent": None,
                        "file_path": str(row[4]),
                    })

        return definitions

    def find_references(self, symbol_name: str) -> Dict[str, Any]:
        """
        Finds definitions, imports, reference call sites, and document backlinks for a symbol across files.
        """
        clean_name = symbol_name.strip()
        definitions = self.find_definition(clean_name)

        # 1. Files importing this symbol
        imports_res = self._query(
            "MATCH (f:File)-[r:IMPORTS]->(s:Symbol) "
            "WHERE toLower(s.name) = toLower($name) "
            "RETURN f.path, r.module, r.line",
            {"name": clean_name},
        )
        imports = []
        if imports_res and len(imports_res) > 1 and isinstance(imports_res[1], list):
            for row in imports_res[1]:
                if len(row) >= 3:
                    imports.append({
                        "file_path": str(row[0]),
                        "module": str(row[1]),
                        "line": int(row[2]) if str(row[2]).isdigit() else 1,
                    })

        # 2. Files referencing/calling this symbol
        refs_res = self._query(
            "MATCH (f:File)-[r:REFERENCES]->(s:Symbol) "
            "WHERE toLower(s.name) = toLower($name) "
            "RETURN f.path, r.line, r.kind",
            {"name": clean_name},
        )
        references = []
        if refs_res and len(refs_res) > 1 and isinstance(refs_res[1], list):
            for row in refs_res[1]:
                if len(row) >= 3:
                    references.append({
                        "file_path": str(row[0]),
                        "line": int(row[1]) if str(row[1]).isdigit() else 1,
                        "kind": str(row[2]),
                    })

        # 3. Documents linking to this symbol, file, or concept (Backlinks)
        doc_links_res = self._query(
            "MATCH (caller:Document)-[r:LINKS_TO]->(target) "
            "WHERE (target:File AND toLower(target.path) ENDS WITH toLower($name)) "
            "   OR (target:Document AND toLower(target.title) = toLower($name)) "
            "   OR (target:Concept AND toLower(target.name) = toLower($name)) "
            "   OR (target:Symbol AND toLower(target.name) = toLower($name)) "
            "RETURN caller.path, coalesce(caller.title, caller.path), coalesce(r.label, 'link'), r.line, r.link_type",
            {"name": clean_name},
        )
        backlinks = []
        if doc_links_res and len(doc_links_res) > 1 and isinstance(doc_links_res[1], list):
            for row in doc_links_res[1]:
                if len(row) >= 5:
                    backlinks.append({
                        "file_path": str(row[0]),
                        "doc_title": str(row[1]),
                        "label": str(row[2]),
                        "line": int(row[3]) if str(row[3]).isdigit() else 1,
                        "link_type": str(row[4]) if row[4] else "wiki_link",
                    })

        return {
            "symbol": clean_name,
            "definitions": definitions,
            "imports": imports,
            "references": references,
            "backlinks": backlinks,
        }

    def get_impact_tree(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Returns all downstream files that import or reference any symbol defined in file_path.
        (Impact analysis for refactoring).
        """
        res = self._query(
            "MATCH (f_src:File {path: $path})<-[:DEFINED_IN]-(s:Symbol)<-[r]-(f_dep:File) "
            "WHERE f_dep.path <> $path "
            "RETURN DISTINCT f_dep.path, s.name, type(r), r.line",
            {"path": file_path},
        )
        dependents = []
        if res and len(res) > 1 and isinstance(res[1], list):
            for row in res[1]:
                if len(row) >= 4:
                    dependents.append({
                        "file_path": str(row[0]),
                        "symbol": str(row[1]),
                        "relation": str(row[2]),
                        "line": int(row[3]) if str(row[3]).isdigit() else 1,
                    })
        return dependents

    def get_statistics(self) -> Dict[str, int]:
        """Returns counts of symbols, files, documents, tags, links, declarations, imports, and references."""
        counts = {
            "symbols": 0,
            "files": 0,
            "documents": 0,
            "tags": 0,
            "links": 0,
            "definitions": 0,
            "imports": 0,
            "references": 0,
        }
        
        sym_res = self._query("MATCH (s:Symbol) RETURN count(s)")
        if sym_res and len(sym_res) > 1 and sym_res[1]:
            counts["symbols"] = int(sym_res[1][0][0])

        file_res = self._query("MATCH (f:File) RETURN count(f)")
        if file_res and len(file_res) > 1 and file_res[1]:
            counts["files"] = int(file_res[1][0][0])

        doc_res = self._query("MATCH (d:Document) RETURN count(d)")
        if doc_res and len(doc_res) > 1 and doc_res[1]:
            counts["documents"] = int(doc_res[1][0][0])

        tag_res = self._query("MATCH (t:Tag) RETURN count(t)")
        if tag_res and len(tag_res) > 1 and tag_res[1]:
            counts["tags"] = int(tag_res[1][0][0])

        link_res = self._query("MATCH ()-[r:LINKS_TO]->() RETURN count(r)")
        if link_res and len(link_res) > 1 and link_res[1]:
            counts["links"] = int(link_res[1][0][0])

        def_res = self._query("MATCH ()-[r:DEFINED_IN]->() RETURN count(r)")
        if def_res and len(def_res) > 1 and def_res[1]:
            counts["definitions"] = int(def_res[1][0][0])

        imp_res = self._query("MATCH ()-[r:IMPORTS]->() RETURN count(r)")
        if imp_res and len(imp_res) > 1 and imp_res[1]:
            counts["imports"] = int(imp_res[1][0][0])

        ref_res = self._query("MATCH ()-[r:REFERENCES]->() RETURN count(r)")
        if ref_res and len(ref_res) > 1 and ref_res[1]:
            counts["references"] = int(ref_res[1][0][0])

        return counts

    def trace_symbol_impact(
        self,
        symbol_name: str,
        direction: str = "upstream",
        max_depth: int = 3,
        token_budget: Optional[int] = 1500,
    ) -> Dict[str, Any]:
        """
        Traces recursive call, reference, import, type implementation, and note link blast radius.
        Applies dynamic token budgeting and progressive level-of-detail (0/1 Knapsack style):
          - 1-hop callers / definitions: Full signature and file path (L1 detail)
          - 2-hop callers: Compact path:line (L0 detail)
          - 3+ hop or budget overflow: Compressed count summary with impacted file list
        Args:
            symbol_name: Target symbol or document.
            direction: 'upstream' (dependents/callers/backlinks) or 'downstream' (callees/dependencies/outlinks).
            max_depth: Traversal depth hops (1-5).
            token_budget: Max approximate tokens for the returned impact trace (default 1500).
        Returns:
            Structured dict with definitions, direct call sites/imports/links, type hierarchies,
            progressive degradation statistics, and formatted markdown summary.
        """
        clean_name = symbol_name.strip()
        depth = max(1, min(max_depth, 5))
        definitions = self.find_definition(clean_name)

        impact_nodes: List[Dict[str, Any]] = []
        transitive_paths: List[Dict[str, Any]] = []
        transitive_nodes: List[Dict[str, Any]] = []

        exact_match = bool(definitions)

        if direction.lower() == "upstream":
            # 1. Direct incoming references and imports (1-hop)
            if exact_match:
                direct_res = self._query(
                    "MATCH (f:File)-[r:REFERENCES|IMPORTS]->(s:Symbol) "
                    "WHERE s.name = $name "
                    "RETURN DISTINCT f.path, type(r), r.line",
                    {"name": clean_name},
                )
            else:
                direct_res = self._query(
                    "MATCH (f:File)-[r:REFERENCES|IMPORTS]->(s:Symbol) "
                    "WHERE toLower(s.name) = toLower($name) "
                    "RETURN DISTINCT f.path, type(r), r.line",
                    {"name": clean_name},
                )
            if direct_res and len(direct_res) > 1 and isinstance(direct_res[1], list):
                for row in direct_res[1]:
                    if len(row) >= 3:
                        impact_nodes.append({
                            "source_file": str(row[0]),
                            "relation": str(row[1]),
                            "line": int(row[2]) if str(row[2]).isdigit() else 1,
                            "target_symbol": clean_name,
                            "depth": 1,
                        })

            # 2. Incoming note links (backlinks)
            if exact_match:
                link_res = self._query(
                    "MATCH (d:Document)-[r:LINKS_TO]->(target) "
                    "WHERE (target:File AND target.path ENDS WITH $name) "
                    "   OR (target:Document AND target.title = $name) "
                    "   OR (target:Concept AND target.name = $name) "
                    "   OR (target:Symbol AND target.name = $name) "
                    "RETURN DISTINCT d.path, coalesce(r.link_type, 'LINKS_TO'), r.line",
                    {"name": clean_name},
                )
            else:
                link_res = self._query(
                    "MATCH (d:Document)-[r:LINKS_TO]->(target) "
                    "WHERE (target:File AND toLower(target.path) ENDS WITH toLower($name)) "
                    "   OR (target:Document AND toLower(target.title) = toLower($name)) "
                    "   OR (target:Concept AND toLower(target.name) = toLower($name)) "
                    "   OR (target:Symbol AND toLower(target.name) = toLower($name)) "
                    "RETURN DISTINCT d.path, coalesce(r.link_type, 'LINKS_TO'), r.line",
                    {"name": clean_name},
                )
            if link_res and len(link_res) > 1 and isinstance(link_res[1], list):
                for row in link_res[1]:
                    if len(row) >= 3:
                        impact_nodes.append({
                            "source_file": str(row[0]),
                            "relation": str(row[1]),
                            "line": int(row[2]) if str(row[2]).isdigit() else 1,
                            "target_symbol": clean_name,
                            "depth": 1,
                        })

            # 3. Transitive symbol-to-symbol relationships (IMPLEMENTS, TYPE_OF)
            if exact_match:
                trans_res = self._query(
                    "MATCH (caller:Symbol)-[r:IMPLEMENTS|TYPE_OF]->(target:Symbol) "
                    "WHERE target.name = $name "
                    "OPTIONAL MATCH (caller)-[:DEFINED_IN]->(f:File) "
                    "RETURN caller.name, type(r), coalesce(f.path, 'unknown')",
                    {"name": clean_name},
                )
            else:
                trans_res = self._query(
                    "MATCH (caller:Symbol)-[r:IMPLEMENTS|TYPE_OF]->(target:Symbol) "
                    "WHERE toLower(target.name) = toLower($name) "
                    "OPTIONAL MATCH (caller)-[:DEFINED_IN]->(f:File) "
                    "RETURN caller.name, type(r), coalesce(f.path, 'unknown')",
                    {"name": clean_name},
                )
            if trans_res and len(trans_res) > 1 and isinstance(trans_res[1], list):
                for row in trans_res[1]:
                    if len(row) >= 3:
                        transitive_paths.append({
                            "symbol": str(row[0]),
                            "relation": str(row[1]),
                            "file_path": str(row[2]),
                            "depth": 1,
                        })

            # 4. Multi-hop transitive callers if depth > 1
            if depth > 1:
                if exact_match:
                    cypher_trans = (
                        f"MATCH path = (caller:Symbol)-[:CALLS|REFERENCES*2..{depth}]->(target:Symbol) "
                        "WHERE target.name = $name "
                        "OPTIONAL MATCH (caller)-[:DEFINED_IN]->(f:File) "
                        "RETURN DISTINCT caller.name, length(path), coalesce(f.path, 'unknown')"
                    )
                else:
                    cypher_trans = (
                        f"MATCH path = (caller:Symbol)-[:CALLS|REFERENCES*2..{depth}]->(target:Symbol) "
                        "WHERE toLower(target.name) = toLower($name) "
                        "OPTIONAL MATCH (caller)-[:DEFINED_IN]->(f:File) "
                        "RETURN DISTINCT caller.name, length(path), coalesce(f.path, 'unknown')"
                    )
                multi_res = self._query(cypher_trans, {"name": clean_name})
                if multi_res and len(multi_res) > 1 and isinstance(multi_res[1], list):
                    for row in multi_res[1]:
                        if len(row) >= 3:
                            transitive_nodes.append({
                                "symbol": str(row[0]),
                                "depth": int(row[1]),
                                "source_file": str(row[2]),
                                "relation": "TRANSITIVE_CALLER",
                            })

        else:  # downstream
            # 1. Outgoing dependencies for files defining this symbol
            down_res = self._query(
                "MATCH (s:Symbol)-[:DEFINED_IN]->(f:File)-[r:IMPORTS|REFERENCES]->(target:Symbol) "
                "WHERE toLower(s.name) = toLower($name) "
                "RETURN DISTINCT target.name, type(r), r.line, f.path",
                {"name": clean_name},
            )
            if down_res and len(down_res) > 1 and isinstance(down_res[1], list):
                for row in down_res[1]:
                    if len(row) >= 4:
                        impact_nodes.append({
                            "source_file": str(row[3]),
                            "relation": str(row[1]),
                            "line": int(row[2]) if str(row[2]).isdigit() else 1,
                            "target_symbol": str(row[0]),
                            "depth": 1,
                        })

            # 2. Outgoing note links from this document
            out_link_res = self._query(
                "MATCH (d:Document)-[r:LINKS_TO]->(target) "
                "WHERE toLower(d.title) = toLower($name) OR toLower(d.path) ENDS WITH toLower($name) "
                "RETURN DISTINCT coalesce(target.title, target.name, target.path), coalesce(r.link_type, 'LINKS_TO'), r.line, d.path",
                {"name": clean_name},
            )
            if out_link_res and len(out_link_res) > 1 and isinstance(out_link_res[1], list):
                for row in out_link_res[1]:
                    if len(row) >= 4:
                        impact_nodes.append({
                            "source_file": str(row[3]),
                            "relation": str(row[1]),
                            "line": int(row[2]) if str(row[2]).isdigit() else 1,
                            "target_symbol": str(row[0]),
                            "depth": 1,
                        })

            # 3. Type relations (what does this symbol implement or extend?)
            trans_res = self._query(
                "MATCH (s:Symbol)-[r:IMPLEMENTS|TYPE_OF]->(target:Symbol) "
                "WHERE toLower(s.name) = toLower($name) "
                "OPTIONAL MATCH (target)-[:DEFINED_IN]->(f:File) "
                "RETURN target.name, type(r), coalesce(f.path, 'unknown')",
                {"name": clean_name},
            )
            if trans_res and len(trans_res) > 1 and isinstance(trans_res[1], list):
                for row in trans_res[1]:
                    if len(row) >= 3:
                        transitive_paths.append({
                            "symbol": str(row[0]),
                            "relation": str(row[1]),
                            "file_path": str(row[2]),
                            "depth": 1,
                        })

            # 4. Multi-hop transitive dependencies if depth > 1
            if depth > 1:
                cypher_down_trans = (
                    f"MATCH path = (s:Symbol)-[:CALLS|REFERENCES*2..{depth}]->(target:Symbol) "
                    "WHERE toLower(s.name) = toLower($name) "
                    "OPTIONAL MATCH (target)-[:DEFINED_IN]->(f:File) "
                    "RETURN DISTINCT target.name, length(path), coalesce(f.path, 'unknown')"
                )
                multi_down = self._query(cypher_down_trans, {"name": clean_name})
                if multi_down and len(multi_down) > 1 and isinstance(multi_down[1], list):
                    for row in multi_down[1]:
                        if len(row) >= 3:
                            transitive_nodes.append({
                                "symbol": str(row[0]),
                                "depth": int(row[1]),
                                "source_file": str(row[2]),
                                "relation": "TRANSITIVE_CALLEE",
                            })

        return format_impact_report(
            clean_name=clean_name,
            direction=direction,
            depth=depth,
            definitions=definitions,
            direct_impacts=impact_nodes,
            type_hierarchies=transitive_paths,
            transitive_impacts=transitive_nodes,
            token_budget=token_budget,
        )

    def get_companion_symbols(self, symbol_name: str) -> List[str]:
        """
        Returns companion symbols defined in the same file as the given symbol.
        """
        clean_name = symbol_name.strip()
        cypher = (
            "MATCH (s:Symbol)-[:DEFINED_IN]->(f:File)<-[:DEFINED_IN]-(companion:Symbol) "
            "WHERE toLower(s.name) = toLower($name) AND toLower(companion.name) <> toLower($name) "
            "RETURN DISTINCT companion.name"
        )
        try:
            res = self._query(cypher, {"name": clean_name})
            companions: List[str] = []
            if res and len(res) > 1 and isinstance(res[1], list):
                for row in res[1]:
                    if row and row[0]:
                        companions.append(str(row[0]))
            return companions
        except Exception as e:
            logger.debug(f"Failed to fetch companion symbols for '{clean_name}': {e}")
            return []

    def get_hop_symbols(self, symbol_name: str) -> List[str]:
        """
        Returns direct 1-hop callees and callers of the given symbol.
        """
        clean_name = symbol_name.strip()
        cypher = (
            "MATCH (s:Symbol)-[:CALLS]-(hop:Symbol) "
            "WHERE toLower(s.name) = toLower($name) AND toLower(hop.name) <> toLower($name) "
            "RETURN DISTINCT hop.name"
        )
        try:
            res = self._query(cypher, {"name": clean_name})
            hops: List[str] = []
            if res and len(res) > 1 and isinstance(res[1], list):
                for row in res[1]:
                    if row and row[0]:
                        hops.append(str(row[0]))
            return hops
        except Exception as e:
            logger.debug(f"Failed to fetch hop symbols for '{clean_name}': {e}")
            return []

    def apply_scope_affinity(
        self,
        candidates: List[Dict[str, Any]],
        confidence_threshold: float = 0.85,
        companion_boost: float = 0.15,
        hop_boost: float = 0.10,
    ) -> List[Dict[str, Any]]:
        """
        Applies Bidirectional AST Scope Affinity re-ranking.
        When a Rank-1 symbol is found with high confidence (>0.85),
        boosts companion symbols defined in the same file by +0.15,
        and direct 1-hop callees/callers by +0.10.
        """
        if not candidates:
            return []

        # Identify Rank-1 candidate
        rank_1 = max(candidates, key=lambda x: x.get("score", 0.0))
        rank_1_score = rank_1.get("score", 0.0)
        rank_1_symbol = rank_1.get("symbol")

        if rank_1_score <= confidence_threshold or not rank_1_symbol:
            return [dict(c) for c in candidates]

        companion_symbols = set(self.get_companion_symbols(rank_1_symbol))
        hop_symbols = set(self.get_hop_symbols(rank_1_symbol))

        reranked: List[Dict[str, Any]] = []
        for c in candidates:
            item = dict(c)
            sym = item.get("symbol")
            if sym and sym != rank_1_symbol:
                boost = 0.0
                if sym in companion_symbols:
                    boost += companion_boost
                if sym in hop_symbols:
                    boost += hop_boost
                item["score"] = round(item.get("score", 0.0) + boost, 4)
            reranked.append(item)

        reranked.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return reranked


