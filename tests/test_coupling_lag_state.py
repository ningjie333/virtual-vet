import math

from src.organs.coupling import CouplingEngine, _CouplingRule


def _make_engine():
    rule = _CouplingRule(
        name="RAAS_SVR_test",
        loop="kidney_cv",
        source_module="kidney",
        source_signal="renin_activity",
        target_module="heart",
        target_param="heart.SVR",
        op="multiply",
        fn_expr="1.0 + 0.20 * min(renin_activity / 1.0, 2.0)",
        condition="renin_activity > 0.1",
        time_constant=10.0,
        priority=10,
        enabled=True,
        references=[],
        notes="",
    )
    engine = object.__new__(CouplingEngine)
    engine._rules = [rule]
    engine._signal_map = {}
    engine._prev_signal_map = {}
    engine._lag_state = {}
    return engine


def test_lag_state_converges_to_target():
    engine = _make_engine()
    dt = 0.1
    tau = 10.0
    target = 2.0
    signal_name = "renin_activity"
    lag_key = f"RAAS_SVR_test:{signal_name}"

    engine._signal_map[signal_name] = 0.0
    engine._lag_state[lag_key] = 0.0

    for step in range(int(5 * tau / dt)):
        if step == int(2 * tau / dt):
            engine._signal_map[signal_name] = target
        prev = engine._lag_state.get(lag_key, target)
        new_lag = prev + (target - prev) * dt / tau
        engine._lag_state[lag_key] = new_lag

    lag = engine._lag_state[lag_key]
    expected_ratio = 1.0 - math.exp(-5.0)
    assert abs(lag / target - expected_ratio) < 0.02


def test_lag_state_dt_invariant():
    tau = 10.0
    target = 2.0
    signal_name = "renin_activity"
    lag_key = f"RAAS_SVR_test:{signal_name}"
    n_tau = 5.0

    def run_lag(dt_val):
        engine = _make_engine()
        n_steps = int(n_tau * tau / dt_val)
        jump_step = int(2 * tau / dt_val)
        for step in range(n_steps):
            if step >= jump_step:
                engine._signal_map[signal_name] = target
            prev = engine._lag_state.get(lag_key, target)
            result = engine._signal_map.get(signal_name, target)
            new_lag = prev + (result - prev) * dt_val / tau
            engine._lag_state[lag_key] = new_lag
        return engine._lag_state[lag_key]

    lag_coarse = run_lag(0.1)
    lag_fine = run_lag(0.01)
    analytical = target * (1.0 - math.exp(-n_tau))
    assert abs(lag_coarse - analytical) / analytical < 0.01
    assert abs(lag_fine - analytical) / analytical < 0.01
    assert abs(lag_fine - lag_coarse) / analytical < 0.01


def test_lag_state_resets_when_target_zero():
    tau = 5.0
    dt = 0.1
    lag_key = "RAAS_SVR_test:renin_activity"

    engine = _make_engine()
    engine._lag_state[lag_key] = 2.0
    engine._signal_map["renin_activity"] = 0.0

    for _ in range(int(5 * tau / dt)):
        prev = engine._lag_state[lag_key]
        new_lag = prev + (0.0 - prev) * dt / tau
        engine._lag_state[lag_key] = new_lag

    assert engine._lag_state[lag_key] < 0.02
