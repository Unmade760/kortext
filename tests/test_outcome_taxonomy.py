"""
Unit tests for mandatory 8-category outcome taxonomy with dual graph-journal persistence.
Verifies task_20c9ea88:
1. Record outcomes with each of the 8 canonical categories to category journal directories.
2. Invalid category raises ValueError.
3. FalkorDB (:Episodic) node has category property and is linked to (:Project) via [:HAS_EPISODE],
   plus [:DECIDES] for decisions and [:MILESTONE] for roadmaps.
"""

import uuid
from datetime import datetime
import pytest
from unittest.mock import patch

from kortext.episodic.driver import AgentNativeEpisodicDriver, VALID_CATEGORIES
from kortext.server import record_system_outcome, CATEGORY_DIRS


@pytest.fixture
def episodic_driver():
    """Provides an isolated AgentNativeEpisodicDriver with an ephemeral FalkorDB graph."""
    test_db = f"test_taxonomy_{uuid.uuid4().hex[:8]}"
    driver = AgentNativeEpisodicDriver(db_name=test_db)
    yield driver
    try:
        driver._get_client().execute_command("GRAPH.DELETE", test_db)
    except Exception:
        pass


@pytest.mark.anyio
async def test_record_all_8_categories_to_journal(tmp_path, monkeypatch):
    """
    Test 1: Record outcomes with each of the 8 categories;
    assert file is created in the appropriate journal/<category_dir>/ directory,
    and daily journal is also updated.
    """
    journal_dir = tmp_path / "journal"
    monkeypatch.setattr("kortext.server.JOURNAL_DIR", journal_dir)

    expected_categories = (
        "decision",
        "roadmap",
        "implementation",
        "experiment",
        "benchmark",
        "investigation",
        "research",
        "report",
    )
    assert VALID_CATEGORIES == expected_categories

    today = datetime.now().strftime("%Y-%m-%d")

    with patch("kortext.server.episodic.record_outcome") as mock_record:
        mock_record.return_value = {
            "entities_written": 1,
            "facts_written": 0,
            "superseded_count": 0,
            "trust_level": "speculative",
            "trust_score": 0.5,
        }

        for cat in VALID_CATEGORIES:
            episode_title = f"Test outcome for {cat}"
            res = await record_system_outcome(
                episode_name=episode_title,
                content=f"Description of {cat} outcome",
                category=cat,
                project="kortext",
            )
            assert f"Recorded: '{episode_title}'" in res

            # Verify outcome file created in category subdirectory
            cat_dir_name = CATEGORY_DIRS[cat]
            target_cat_dir = journal_dir / cat_dir_name
            assert target_cat_dir.is_dir(), f"Expected directory {target_cat_dir} to exist"

            category_files = list(target_cat_dir.glob("*.md"))
            assert len(category_files) == 1, f"Expected 1 file in {target_cat_dir}, found {category_files}"
            content = category_files[0].read_text()
            assert episode_title in content
            assert cat in content

    # Assert daily journal file also exists and has entries
    daily_journal = journal_dir / f"{today}.md"
    assert daily_journal.is_file()
    daily_content = daily_journal.read_text()
    for cat in VALID_CATEGORIES:
        assert f"Test outcome for {cat}" in daily_content


@pytest.mark.anyio
async def test_invalid_category_raises_value_error(episodic_driver):
    """
    Test 2: Assert that invalid category raises ValueError in both server and driver.
    """
    # Test server.record_system_outcome with invalid category
    with pytest.raises(ValueError) as excinfo_server:
        await record_system_outcome(
            episode_name="Invalid Category Test",
            content="Testing invalid category",
            category="non_existent_category",
        )
    assert "Invalid category 'non_existent_category'" in str(excinfo_server.value)

    # Test driver.record_outcome with invalid category
    with pytest.raises(ValueError) as excinfo_driver:
        await episodic_driver.record_outcome(
            episode_name="Invalid Category Driver Test",
            content="Testing invalid category in driver",
            category="bogus",
        )
    assert "Invalid category 'bogus'" in str(excinfo_driver.value)

    # Test with non-string / None category
    with pytest.raises(ValueError):
        await episodic_driver.record_outcome(
            episode_name="None Category Driver Test",
            content="Testing None category",
            category=None,
        )


@pytest.mark.asyncio
async def test_falkordb_episodic_node_category_and_project_link(episodic_driver):
    """
    Test 3: Assert FalkorDB (:Episodic) node has category property and is linked to (:Project) via [:HAS_EPISODE].
    Also verifies (:DECIDES) edge for decision without entities and (:MILESTONE) edge for roadmap.
    """
    # 1. Implementation outcome
    res_impl = await episodic_driver.record_outcome(
        episode_name="Feature Implementation",
        content="Implemented feature X",
        category="implementation",
        project="cortex_project",
    )
    assert res_impl["status"] == "ok"

    # Verify (:Episodic) node has category and is linked to (:Project) via [:HAS_EPISODE]
    query_impl = """
    MATCH (p:Project {id: $proj})-[:HAS_EPISODE]->(e:Episodic {name: $ename})
    RETURN e.category, p.id
    """
    data_impl = episodic_driver._query(
        query_impl,
        {"proj": "cortex_project", "ename": "Feature Implementation"},
    )
    assert data_impl and len(data_impl) > 1 and data_impl[1]
    assert data_impl[1][0][0] == "implementation"
    assert data_impl[1][0][1] == "cortex_project"

    # 2. Decision outcome without entities -> creates ADR entity node and [:DECIDES] link
    res_dec = await episodic_driver.record_outcome(
        episode_name="ADR 001 Architecture Choice",
        content="Chose FalkorDB for Graph substrate",
        category="decision",
        project="cortex_project",
    )
    assert res_dec["status"] == "ok"

    query_adr = """
    MATCH (e:Episodic {name: $ename})-[:DECIDES]->(adr)
    RETURN adr.name, adr.entity_type
    """
    data_adr = episodic_driver._query(
        query_adr,
        {"ename": "ADR 001 Architecture Choice"},
    )
    assert data_adr and len(data_adr) > 1 and data_adr[1]
    assert data_adr[1][0][0] == "ADR 001 Architecture Choice"
    assert data_adr[1][0][1] == "adr"

    # 3. Roadmap outcome -> creates Milestone entity node and [:MILESTONE] link
    res_road = await episodic_driver.record_outcome(
        episode_name="Q4 Alpha Release",
        content="Targeting alpha release by end of Q4",
        category="roadmap",
        project="cortex_project",
    )
    assert res_road["status"] == "ok"

    query_milestone = """
    MATCH (e:Episodic {name: $ename})-[:MILESTONE]->(m)
    RETURN m.name, m.entity_type
    """
    data_milestone = episodic_driver._query(
        query_milestone,
        {"ename": "Q4 Alpha Release"},
    )
    assert data_milestone and len(data_milestone) > 1 and data_milestone[1]
    assert data_milestone[1][0][0] == "Q4 Alpha Release"
    assert data_milestone[1][0][1] == "milestone"

    # 4. Decision outcome WITH entities provided -> does not create auto ADR node
    res_dec_with_ent = await episodic_driver.record_outcome(
        episode_name="ADR 002 Component Modularity",
        content="Explicit entity provided",
        category="decision",
        project="cortex_project",
        entities=[{"name": "ModularitySpec", "type": "spec", "summary": "Module boundaries"}],
    )
    assert res_dec_with_ent["status"] == "ok"
    data_dec_ent = episodic_driver._query(
        "MATCH (e:Episodic {name: $ename})-[:DECIDES]->(adr) RETURN adr.name",
        {"ename": "ADR 002 Component Modularity"},
    )
    assert not data_dec_ent or len(data_dec_ent) <= 1 or not data_dec_ent[1]

