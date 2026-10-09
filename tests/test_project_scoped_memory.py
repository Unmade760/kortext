"""
Unit tests for project-scoped episodic memory and search filtering.
Verifies task_3c785fa3:
1. r.project persisted on [:RELATES_TO] edges in record_outcome and record_fact.
2. Filtering search by project (case-insensitive, handling 'all' or None).
3. Filtering query_facts_as_of and query_multi_hop_facts by project.
"""

import uuid
import pytest
from kortext.episodic.driver import AgentNativeEpisodicDriver


@pytest.fixture
def episodic_driver():
    """Provides an isolated AgentNativeEpisodicDriver with an ephemeral FalkorDB graph."""
    test_db = f"test_scoped_{uuid.uuid4().hex[:8]}"
    driver = AgentNativeEpisodicDriver(db_name=test_db)
    yield driver
    try:
        driver._get_client().execute_command("GRAPH.DELETE", test_db)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_record_facts_scoped_by_project(episodic_driver):
    """
    Test 1: Record fact A for project='project_alpha' and fact B for project='project_beta'.
    Verifies that r.project is correctly set on [:RELATES_TO] edges in the graph.
    """
    fact_a_id = episodic_driver.record_fact(
        subject="ServiceA",
        relation="USES_PORT",
        fact="ServiceA uses port 8080 for HTTP traffic",
        object_name="Port8080",
        project="project_alpha",
    )
    assert fact_a_id is not None

    fact_b_id = episodic_driver.record_fact(
        subject="ServiceB",
        relation="USES_PORT",
        fact="ServiceB uses port 9090 for gRPC traffic",
        object_name="Port9090",
        project="project_beta",
    )
    assert fact_b_id is not None

    # Inspect the raw graph edges
    res_a = episodic_driver._query(
        "MATCH ()-[r:RELATES_TO {id: $fid}]->() RETURN r.project",
        {"fid": fact_a_id},
    )
    assert res_a and len(res_a) > 1 and res_a[1]
    assert res_a[1][0][0] == "project_alpha"

    res_b = episodic_driver._query(
        "MATCH ()-[r:RELATES_TO {id: $fid}]->() RETURN r.project",
        {"fid": fact_b_id},
    )
    assert res_b and len(res_b) > 1 and res_b[1]
    assert res_b[1][0][0] == "project_beta"


@pytest.mark.asyncio
async def test_search_scoped_to_project_alpha(episodic_driver):
    """
    Test 2: Search with project='project_alpha' -> verifies fact A is returned, fact B is NOT returned.
    """
    episodic_driver.record_fact(
        subject="AlphaModule",
        relation="DEPENDS_ON",
        fact="AlphaModule depends on CoreAuth library",
        object_name="CoreAuth",
        project="project_alpha",
    )
    episodic_driver.record_fact(
        subject="BetaModule",
        relation="DEPENDS_ON",
        fact="BetaModule depends on CoreAuth library",
        object_name="CoreAuth",
        project="project_beta",
    )

    results = await episodic_driver.search(
        query="CoreAuth library",
        project="project_alpha",
    )
    assert any("AlphaModule" in r for r in results)
    assert not any("BetaModule" in r for r in results)


@pytest.mark.asyncio
async def test_search_scoped_to_project_beta(episodic_driver):
    """
    Test 3: Search with project='project_beta' -> verifies fact B is returned, fact A is NOT returned.
    """
    episodic_driver.record_fact(
        subject="AlphaConfig",
        relation="CONFIGURES",
        fact="AlphaConfig configures database pool settings",
        object_name="DatabasePool",
        project="project_alpha",
    )
    episodic_driver.record_fact(
        subject="BetaConfig",
        relation="CONFIGURES",
        fact="BetaConfig configures database pool settings",
        object_name="DatabasePool",
        project="project_beta",
    )

    results = await episodic_driver.search(
        query="database pool",
        project="project_beta",
    )
    assert any("BetaConfig" in r for r in results)
    assert not any("AlphaConfig" in r for r in results)


@pytest.mark.asyncio
async def test_search_all_returns_both(episodic_driver):
    """
    Test 4: Search with project='all' -> verifies both facts can be retrieved.
    Also verifies project=None retrieves both facts.
    """
    episodic_driver.record_fact(
        subject="AlphaService",
        relation="CONNECTS_TO",
        fact="AlphaService connects to SharedQueue system",
        object_name="SharedQueue",
        project="project_alpha",
    )
    episodic_driver.record_fact(
        subject="BetaService",
        relation="CONNECTS_TO",
        fact="BetaService connects to SharedQueue system",
        object_name="SharedQueue",
        project="project_beta",
    )

    # project="all"
    results_all = await episodic_driver.search(
        query="SharedQueue",
        project="all",
    )
    assert any("AlphaService" in r for r in results_all)
    assert any("BetaService" in r for r in results_all)

    # project=None
    results_none = await episodic_driver.search(
        query="SharedQueue",
        project=None,
    )
    assert any("AlphaService" in r for r in results_none)
    assert any("BetaService" in r for r in results_none)


@pytest.mark.asyncio
async def test_record_outcome_scopes_relates_to_edges(episodic_driver):
    """
    Verifies that record_outcome persists r.project on every [:RELATES_TO] edge created.
    Also tests default project behavior when unspecified.
    """
    # 1. With explicit project
    res = await episodic_driver.record_outcome(
        episode_name="DeployOutcomeAlpha",
        content="Deployed alpha release successfully",
        project="project_alpha",
        entities=[{"name": "AlphaDeploy", "summary": "Deployment entity"}],
        facts=[{
            "source": "AlphaDeploy",
            "relation": "TARGETS",
            "target": "ClusterOne",
            "fact": "AlphaDeploy targets ClusterOne environment",
        }],
    )
    assert res["status"] == "ok"

    check_a = episodic_driver._query(
        "MATCH (s:Entity {name: 'AlphaDeploy'})-[r:RELATES_TO]->(t:Entity {name: 'ClusterOne'}) "
        "RETURN r.project"
    )
    assert check_a and len(check_a) > 1 and check_a[1]
    assert check_a[1][0][0] == "project_alpha"

    # 2. Without project specified -> defaults to 'kortext'
    res_default = await episodic_driver.record_outcome(
        episode_name="DefaultOutcome",
        content="Default outcome content",
        project=None,
        entities=[{"name": "DefaultEnt", "summary": "Default entity"}],
        facts=[{
            "source": "DefaultEnt",
            "relation": "TARGETS",
            "target": "DefaultCluster",
            "fact": "DefaultEnt targets DefaultCluster environment",
        }],
    )
    assert res_default["status"] == "ok"

    check_default = episodic_driver._query(
        "MATCH (s:Entity {name: 'DefaultEnt'})-[r:RELATES_TO]->(t:Entity {name: 'DefaultCluster'}) "
        "RETURN r.project"
    )
    assert check_default and len(check_default) > 1 and check_default[1]
    assert check_default[1][0][0] == "kortext"


@pytest.mark.asyncio
async def test_query_facts_as_of_project_scoping(episodic_driver):
    """
    Verifies query_facts_as_of filters facts by project.
    """
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    t1 = (now - timedelta(hours=2)).isoformat()

    episodic_driver.record_fact(
        subject="SharedEntity",
        relation="HOSTED_ON",
        fact="SharedEntity hosted on AlphaHost",
        object_name="AlphaHost",
        valid_from=t1,
        project="project_alpha",
    )
    episodic_driver.record_fact(
        subject="SharedEntity",
        relation="HOSTED_ON",
        fact="SharedEntity hosted on BetaHost",
        object_name="BetaHost",
        valid_from=t1,
        project="project_beta",
    )

    t_query = now.isoformat()

    # Scope to alpha
    alpha_facts = episodic_driver.query_facts_as_of(
        subject="SharedEntity",
        as_of_date=t_query,
        project="project_alpha",
    )
    assert len(alpha_facts) == 1
    assert "AlphaHost" in alpha_facts[0]["fact"]

    # Scope to beta
    beta_facts = episodic_driver.query_facts_as_of(
        subject="SharedEntity",
        as_of_date=t_query,
        project="project_beta",
    )
    assert len(beta_facts) == 1
    assert "BetaHost" in beta_facts[0]["fact"]

    # Scope to all
    all_facts = episodic_driver.query_facts_as_of(
        subject="SharedEntity",
        as_of_date=t_query,
        project="all",
    )
    assert len(all_facts) == 2


@pytest.mark.asyncio
async def test_query_multi_hop_facts_project_scoping(episodic_driver):
    """
    Verifies query_multi_hop_facts filters 1-hop and 2-hop traversals by project.
    """
    # Project Alpha path: NodeA -> NodeB -> NodeC
    episodic_driver.record_fact(
        subject="NodeA",
        relation="LINKS_TO",
        fact="NodeA links to NodeB in alpha",
        object_name="NodeB",
        project="project_alpha",
    )
    episodic_driver.record_fact(
        subject="NodeB",
        relation="LINKS_TO",
        fact="NodeB links to NodeC in alpha",
        object_name="NodeC",
        project="project_alpha",
    )

    # Project Beta path: NodeA -> NodeB_Beta -> NodeC_Beta
    episodic_driver.record_fact(
        subject="NodeA",
        relation="LINKS_TO",
        fact="NodeA links to NodeB_Beta in beta",
        object_name="NodeB_Beta",
        project="project_beta",
    )

    alpha_hops = episodic_driver.query_multi_hop_facts(
        entity_name="NodeA",
        max_hops=2,
        project="project_alpha",
    )
    assert any("NodeB" in f["fact"] and "Beta" not in f["fact"] for f in alpha_hops)
    assert not any("NodeB_Beta" in f["fact"] for f in alpha_hops)

    beta_hops = episodic_driver.query_multi_hop_facts(
        entity_name="NodeA",
        max_hops=2,
        project="project_beta",
    )
    assert any("NodeB_Beta" in f["fact"] for f in beta_hops)
    assert not any("NodeB links to NodeC" in f["fact"] for f in beta_hops)
