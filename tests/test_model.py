from evac.model import INF, Scenario, build_map, run


def test_deterministic():
    sc = Scenario(n_agents=100, seed=1)
    assert run(sc) == run(sc)


def test_shelters_reachable_from_coast():
    _, _, dist = build_map(3, 2)
    assert dist[40, 20] < INF


def test_earlier_warning_saves_more():
    early = run(Scenario(n_agents=300, warning_delay_min=0, seed=3))["survival_rate"]
    late = run(Scenario(n_agents=300, warning_delay_min=20, seed=3))["survival_rate"]
    assert early >= late


def test_survival_in_range():
    assert 0.0 <= run(Scenario(n_agents=50))["survival_rate"] <= 1.0
