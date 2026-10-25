from unittest.mock import MagicMock, patch
import pytest

from kortext.dashboard.views import (
    DEFAULT_REL_SPEC,
    EDGE_STYLES,
    REL_SPECS,
    NODE_LEVEL_SPECS,
    _make_vis_edge,
    _make_vis_node,
    populate_clean_symbols_graph,
    build_graph_view,
    build_symbol_impact_view,
)


def test_rel_specs_structure():
    """Verify that REL_SPECS defines canonical relations and styles."""
    expected_rels = [
        "DEFINED_IN",
        "REFERENCES",
        "IMPORTS",
        "IMPLEMENTS",
        "TYPE_OF",
        "LINKS_TO",
        "TAG",
        "RELATES_TO",
        "BELONGS_TO",
        "SUPERSEDES",
        "MENTIONS",
    ]
    for rel in expected_rels:
        assert rel in REL_SPECS, f"Missing relation spec: {rel}"
        spec = REL_SPECS[rel]
        assert "width" in spec
        assert "color" in spec
        assert "highlight" in spec
        assert "hover" in spec
        assert "font_color" in spec
        assert "bg" in spec

    # Backward compatibility
    assert EDGE_STYLES == REL_SPECS


def test_make_vis_edge():
    """Verify _make_vis_edge formats Vis.js edge with design palette."""
    edge = _make_vis_edge("kortext/app.py", "kortext/tools.py", "IMPORTS")
    assert edge["from"] == "kortext/app.py"
    assert edge["to"] == "kortext/tools.py"
    assert edge["label"] == "IMPORTS"
    assert edge["width"] == REL_SPECS["IMPORTS"]["width"]
    assert edge["color"]["color"] == REL_SPECS["IMPORTS"]["color"]
    assert edge["color"]["highlight"] == REL_SPECS["IMPORTS"]["highlight"]
    assert "dashes" not in edge  # IMPORTS has dashes=False

    # IMPLEMENTS has dashes
    dashed_edge = _make_vis_edge("ClassA", "InterfaceB", "IMPLEMENTS")
    assert dashed_edge["dashes"] == [6, 4]


def test_make_vis_edge_custom_properties():
    """Verify _make_vis_edge supports title, dashes, color, font_color, and extra_props."""
    # Test with string color
    edge_str_color = _make_vis_edge(
        "A", "B", "CALLS",
        title="Custom Title",
        dashes=[2, 2],
        color="#ef4444",
        font_color="#f87171",
        extra_props={"custom_flag": True, "smooth": {"type": "continuous", "roundness": 0.25}}
    )
    assert edge_str_color["title"] == "Custom Title"
    assert edge_str_color["dashes"] == [2, 2]
    assert edge_str_color["color"]["color"] == "#ef4444"
    assert edge_str_color["font"]["color"] == "#f87171"
    assert edge_str_color["custom_flag"] is True
    assert edge_str_color["smooth"]["roundness"] == 0.25

    # Test with dict color
    edge_dict_color = _make_vis_edge(
        "A", "B", "CALLS",
        color={"color": "#10b981", "highlight": "#34d399"},
        extra_props={"is_mention": True}
    )
    assert edge_dict_color["color"]["color"] == "#10b981"
    assert edge_dict_color["color"]["highlight"] == "#34d399"
    assert edge_dict_color["color"]["hover"] == "#34d399"
    assert edge_dict_color["is_mention"] is True


def test_populate_clean_symbols_graph():
    """Verify declarative populator for clean symbols view."""
    mock_redis = MagicMock()

    def fake_execute_command(cmd, db, query):
        if "-[d:DEFINED_IN]->" in query:
            return ["header", [["my_func", "kortext/test.py", "function", 42]]]
        if "-[r:REFERENCES]->" in query:
            return ["header", [["kortext/test.py", "my_func", 50]]]
        if "-[r:IMPORTS]->" in query:
            return ["header", [["kortext/test.py", "my_func", 1]]]
        if "-[r:IMPLEMENTS]->" in query:
            return ["header", [["DerivedClass", "BaseClass"]]]
        if "-[r:TYPE_OF]->" in query:
            return ["header", [["DerivedClass", "CustomType"]]]
        if "-[r:LINKS_TO]->" in query:
            return ["header", [["docs/spec.md", "Spec Document", "kortext/test.py", "test.py", "file", "links_to", "link"]]]
        if "-[r:HAS_TAG]->" in query:
            return ["header", [["docs/spec.md", "Spec Document", "core-arch"]]]
        if "-[r:BELONGS_TO]->" in query:
            return ["header", [["kortext/test.py", "sub_1", "TestSub", "Description of Subsystem"]]]
        return ["header", []]

    mock_redis.execute_command.side_effect = fake_execute_command

    nodes_dict = {}
    edges_list = []
    sym_to_file = {}

    populate_clean_symbols_graph(mock_redis, "test_db", nodes_dict, edges_list, sym_to_file)

    # Node assertions
    assert "my_func" in nodes_dict
    assert nodes_dict["my_func"]["group"] == "symbol"
    assert "kortext/test.py" in nodes_dict
    assert nodes_dict["kortext/test.py"]["group"] == "file"
    assert "DerivedClass" in nodes_dict
    assert "BaseClass" in nodes_dict
    assert "docs/spec.md" in nodes_dict
    assert nodes_dict["docs/spec.md"]["group"] == "document"
    assert "tag:core-arch" in nodes_dict
    assert nodes_dict["tag:core-arch"]["group"] == "tag"
    assert "sub_1" in nodes_dict
    assert nodes_dict["sub_1"]["group"] == "subsystem"

    # Edge assertions
    edge_labels = [e["label"] for e in edges_list]
    assert "DEFINED_IN" in edge_labels
    assert "REFERENCES" in edge_labels
    assert "IMPORTS" in edge_labels
    assert "IMPLEMENTS" in edge_labels
    assert "TYPE_OF" in edge_labels
    assert "LINKS_TO" in edge_labels
    assert "TAG" in edge_labels
    assert "BELONGS_TO" in edge_labels


def test_build_graph_view_clean_symbols():
    """Verify build_graph_view output schema in clean symbols mode."""
    with patch("kortext.dashboard.views.get_shared_falkordb_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_redis = MagicMock()
        mock_client.get_redis.return_value = mock_redis
        mock_client_factory.return_value = mock_client

        def fake_execute(cmd, db, query):
            if "-[d:DEFINED_IN]->" in query:
                return ["header", [["my_func", "kortext/test.py", "function", 42]]]
            return ["header", []]

        mock_redis.execute_command.side_effect = fake_execute

        res = build_graph_view("localhost", 6379, "kortext", graph_type="symbols", clean=True)
        assert res["status"] == "ok"
        assert res["graph_type"] == "symbols"
        assert len(res["nodes"]) == 2
        assert len(res["edges"]) == 1
        assert res["stats"]["nodes_count"] == 2
        assert res["stats"]["edges_count"] == 1

        # Check node enrichment (degree and cluster)
        for n in res["nodes"]:
            assert "degree" in n
            assert "cluster_id" in n
            assert "cluster_name" in n


def test_build_graph_view_raw_symbols():
    """Verify build_graph_view output schema in raw symbols mode."""
    with patch("kortext.dashboard.views.get_shared_falkordb_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_redis = MagicMock()
        mock_client.get_redis.return_value = mock_redis
        mock_client_factory.return_value = mock_client

        def fake_execute(cmd, db, query):
            if "MATCH (n) RETURN" in query:
                return ["header", [["my_func", "Symbol"]]]
            if "MATCH (s)-[r]->(t)" in query:
                return ["header", [["my_func", "RELATES_TO", "kortext/test.py"]]]
            return ["header", []]

        mock_redis.execute_command.side_effect = fake_execute

        res = build_graph_view("localhost", 6379, "kortext", graph_type="symbols", clean=False)
        assert res["status"] == "ok"
        assert len(res["nodes"]) == 2
        assert len(res["edges"]) == 1
        edge = res["edges"][0]
        assert edge["label"] == "RELATES_TO"
        assert edge["color"]["color"] == REL_SPECS["RELATES_TO"]["color"]


def test_build_graph_view_episodic():
    """Verify build_graph_view output schema in episodic mode."""
    with patch("kortext.dashboard.views.get_shared_falkordb_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_redis = MagicMock()
        mock_client.get_redis.return_value = mock_redis
        mock_client_factory.return_value = mock_client

        def fake_execute(cmd, db, query):
            if "MATCH (n) RETURN" in query:
                return ["header", [["EntityA", "Episodic"], ["EntityB", "Entity"]]]
            if "MATCH (s)-[r]->(t)" in query:
                return ["header", [["EntityA", "SUPERSEDES", "EntityB"]]]
            return ["header", []]

        mock_redis.execute_command.side_effect = fake_execute

        res = build_graph_view("localhost", 6379, "kortext", graph_type="episodic")
        assert res["status"] == "ok"
        assert len(res["nodes"]) == 2
        assert len(res["edges"]) == 1
        edge = res["edges"][0]
        assert edge["label"] == "SUPERSEDES"
        assert edge["width"] == REL_SPECS["SUPERSEDES"]["width"]
        assert edge["dashes"] == REL_SPECS["SUPERSEDES"]["dashes"]
        assert edge["color"]["color"] == REL_SPECS["SUPERSEDES"]["color"]


def test_make_vis_node_basic():
    """Verify _make_vis_node creates canonical node dict without level styling."""
    node = _make_vis_node(
        node_id="kortext/tools.py",
        label="tools.py",
        group="file",
        title="<b>File: tools.py</b>",
    )
    assert node["id"] == "kortext/tools.py"
    assert node["label"] == "tools.py"
    assert node["full_name"] == "kortext/tools.py"
    assert node["group"] == "file"
    assert node["title"] == "<b>File: tools.py</b>"
    # Unspecified visual properties should not be populated
    assert "color" not in node
    assert "level" not in node
    assert "shape" not in node
    assert "shadow" not in node


def test_make_vis_node_levels():
    """Verify _make_vis_node declarative level styling defaults."""
    # Level 0 (Target)
    n0 = _make_vis_node(node_id="target_sym", label="target_sym", level=0)
    assert n0["level"] == 0
    assert n0["shape"] == "box"
    assert n0["shapeProperties"] == {"borderRadius": 6}
    assert n0["color"] == NODE_LEVEL_SPECS[0]["color"]
    assert n0["shadow"] == NODE_LEVEL_SPECS[0]["shadow"]
    assert n0["margin"] == 10
    assert n0["borderWidth"] == 2.5
    assert n0["font"]["bold"] is True

    # Level 1 (Direct Impact)
    n1 = _make_vis_node(node_id="dep_file", label="dep_file", level=1)
    assert n1["level"] == 1
    assert n1["color"] == NODE_LEVEL_SPECS[1]["color"]
    assert n1["shadow"] == NODE_LEVEL_SPECS[1]["shadow"]
    assert n1["margin"] == 8
    assert n1["borderWidth"] == 2

    # Level 2 (Type Hierarchy)
    n2 = _make_vis_node(node_id="type_sym", label="type_sym", level=2)
    assert n2["level"] == 2
    assert n2["color"] == NODE_LEVEL_SPECS[2]["color"]
    assert n2["borderWidth"] == 1.8


def test_make_vis_node_custom_properties():
    """Verify _make_vis_node allows explicit property overrides and extra_props."""
    custom_color = {"background": "#123456", "border": "#654321"}
    custom_shadow = {"enabled": False}
    custom_font = {"color": "#abcdef", "size": 14}
    node = _make_vis_node(
        node_id="custom_id",
        label="custom_label",
        full_name="Custom Full Name",
        group="custom_group",
        level=1,
        color=custom_color,
        shadow=custom_shadow,
        margin=12,
        border_width=3.0,
        font=custom_font,
        shape="ellipse",
        shape_properties={"borderDashes": [2, 2]},
        extra_props={"custom_tag": "vip", "opacity": 0.9},
    )
    assert node["id"] == "custom_id"
    assert node["label"] == "custom_label"
    assert node["full_name"] == "Custom Full Name"
    assert node["group"] == "custom_group"
    assert node["level"] == 1
    assert node["color"] == custom_color
    assert node["shadow"] == custom_shadow
    assert node["margin"] == 12
    assert node["borderWidth"] == 3.0
    assert node["font"] == custom_font
    assert node["shape"] == "ellipse"
    assert node["shapeProperties"] == {"borderDashes": [2, 2]}
    assert node["custom_tag"] == "vip"
    assert node["opacity"] == 0.9


def test_build_symbol_impact_view_file_target():
    """Verify build_symbol_impact_view formats file blast radius with _make_vis_node."""
    with patch("kortext.dashboard.views.SymbolGraphManager") as mock_mgr_cls:
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_impact_tree.return_value = [
            {"file_path": "kortext/caller.py", "symbol": "my_func", "relation": "DEPENDS_ON", "line": 42}
        ]

        res = build_symbol_impact_view(
            target="kortext/target.py",
            file_path=None,
            symbol=None,
            direction="upstream",
            max_depth=2,
            host="localhost",
            port=6379,
        )
        assert res["status"] == "ok"
        assert len(res["nodes"]) == 2
        assert len(res["edges"]) == 1
        assert res["summary"]["direct_impact_count"] == 1

        nodes_by_id = {n["id"]: n for n in res["nodes"]}
        target_node = nodes_by_id["kortext/target.py"]
        assert target_node["level"] == 0
        assert target_node["shape"] == "box"
        assert target_node["shapeProperties"]["borderRadius"] == 6
        assert target_node["borderWidth"] == 2.5

        dep_node = nodes_by_id["kortext/caller.py"]
        assert dep_node["level"] == 1
        assert dep_node["shape"] == "box"
        assert dep_node["borderWidth"] == 2


def test_build_symbol_impact_view_symbol_target():
    """Verify build_symbol_impact_view formats symbol blast radius with _make_vis_node."""
    with patch("kortext.dashboard.views.SymbolGraphManager") as mock_mgr_cls:
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.trace_symbol_impact.return_value = {
            "definitions": [{"source_file": "kortext/def.py", "line": 10}],
            "direct_impacts": [{"source_file": "kortext/caller.py", "relation": "CALLS", "line": 15}],
            "type_hierarchies": [{"symbol": "BaseClass", "relation": "IMPLEMENTS", "file_path": "kortext/base.py"}],
        }

        res = build_symbol_impact_view(
            target="MySymbol",
            file_path=None,
            symbol=None,
            direction="upstream",
            max_depth=1,
            host="localhost",
            port=6379,
        )
        assert res["status"] == "ok"
        assert len(res["nodes"]) == 3
        assert len(res["edges"]) == 2

        nodes_by_id = {n["id"]: n for n in res["nodes"]}
        assert "MySymbol" in nodes_by_id
        assert nodes_by_id["MySymbol"]["level"] == 0
        assert "kortext/caller.py" in nodes_by_id
        assert nodes_by_id["kortext/caller.py"]["level"] == 1
        assert "BaseClass" in nodes_by_id
        assert nodes_by_id["BaseClass"]["level"] == 2


def test_build_symbol_impact_view_with_real_graph_traversal():
    """Verify build_symbol_impact_view executes SymbolGraphManager.trace_symbol_impact without NameError."""
    from kortext.symbols.graph import SymbolGraphManager

    mock_client = MagicMock()
    mock_redis = MagicMock()
    mock_client.get_redis.return_value = mock_redis
    mock_client.query.return_value = [[], []]
    mock_redis.execute_command.return_value = [[], []]

    with patch("kortext.dashboard.views.impact._get_symbol_graph_manager") as mock_mgr_getter, \
         patch("kortext.dashboard.views.impact._get_falkordb_client") as mock_client_getter:
        mgr = SymbolGraphManager(client=mock_client)
        mock_mgr_getter.return_value = mgr
        mock_client_getter.return_value = mock_client

        res = build_symbol_impact_view(
            target="MySymbol",
            file_path=None,
            symbol=None,
            direction="upstream",
            max_depth=1,
            host="localhost",
            port=6379,
        )

        assert res["status"] == "ok"
        assert res["summary"]["target"] == "MySymbol"
        assert res["summary"]["type"] == "symbol"

