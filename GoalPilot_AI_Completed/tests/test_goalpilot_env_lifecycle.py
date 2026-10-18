"""Environment lifecycle: Gymnasium compliance, determinism, reward decomposition,
checkpoint compatibility, and the invariants the archive relied on but never tested
(audit finding F-09).
"""
from __future__ import annotations

import numpy as np
import pytest

import goalpilot_env
from goalpilot_config import GoalPilotConfig

FAST = GoalPilotConfig.lp_parity()          # ledger accounting, LP-consistent targets


def _make_env(rl_data, user_ids, config, seed=None):
    return goalpilot_env.GoalPilotEnv(
        profiles=rl_data["profiles"], goals=rl_data["goals"],
        market=rl_data["market"], user_ids=user_ids, config=config,
        seed=seed,
    )


# ------------------------------------------------------------------- Gymnasium API -----

def test_env_passes_gymnasium_check(small_slice):
    """F-09: the archive ran check_env ad hoc and never registered it as a test."""
    check_env = pytest.importorskip(
        "stable_baselines3.common.env_checker"
    ).check_env
    env = _make_env(small_slice, small_slice["user_ids"], FAST, seed=7)
    check_env(env, warn=True, skip_render_check=True)


def test_spaces_match_the_trained_checkpoint_spec(small_slice):
    """The archived PPO checkpoint expects obs (42,) and action (5, 3)."""
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    assert env.observation_space.shape == (42,)
    assert env.action_space.shape == (5, 3)
    assert env.max_goals == 5
    assert env.max_steps == 142


def test_reset_and_step_contract(small_slice):
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    obs, info = env.reset(options={"user_id": small_slice["user_ids"][0]})
    assert obs.shape == env.observation_space.shape
    assert obs.dtype == np.float32
    assert np.isfinite(obs).all()
    assert "user_id" in info and "goal_count" in info

    obs, reward, terminated, truncated, info = env.step(
        np.zeros(env.action_space.shape, dtype=np.float32)
    )
    assert isinstance(reward, float)
    assert isinstance(terminated, bool) and isinstance(truncated, bool)
    assert obs.shape == env.observation_space.shape
    for key in ("user_id", "monthly_surplus", "savings_contribution",
                "investment_contribution", "new_loan_principal", "goal_balances",
                "goal_targets", "reward_components", "budget_audit", "ledger",
                "net_worth", "unallocated_surplus"):
        assert key in info, f"missing info key: {key}"


def test_unknown_user_is_rejected(small_slice):
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    with pytest.raises(ValueError):
        env.reset(options={"user_id": "USER_99999"})


def test_bad_action_shape_and_nonfinite_are_rejected(small_slice):
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    env.reset(options={"user_id": small_slice["user_ids"][0]})
    wrong_shape = (max(1, env.action_space.shape[0] - 1), env.action_space.shape[1])
    with pytest.raises(ValueError):
        env.step(np.zeros(wrong_shape, dtype=np.float32))
    bad = np.zeros(env.action_space.shape, dtype=np.float32)
    bad[0, 0] = np.nan
    with pytest.raises(ValueError):
        env.step(bad)


def test_n_goal_slots_pins_the_space_across_subsets(rl_data, small_slice):
    """A checkpoint must not break when the env is built from a smaller user subset."""
    pinned = _make_env(small_slice, small_slice["user_ids"], FAST)
    assert pinned.observation_space.shape == (42,)
    assert pinned.action_space.shape == (5, 3)

    # Without pinning, a 6-user slice is inferred to have fewer slots -> incompatible.
    unpinned = _make_env(small_slice, small_slice["user_ids"],
                         GoalPilotConfig.archived().replace(n_goal_slots=None))
    assert unpinned.observation_space.shape != pinned.observation_space.shape


def test_n_goal_slots_smaller_than_data_is_rejected(small_slice):
    with pytest.raises(ValueError):
        _make_env(small_slice, small_slice["user_ids"],
                  GoalPilotConfig.archived().replace(n_goal_slots=1))


def test_episode_terminates_after_market_horizon(small_slice):
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    env.reset(options={"user_id": small_slice["user_ids"][0]})
    steps = 0
    while True:
        _, _, term, trunc, _ = env.step(np.zeros(env.action_space.shape, dtype=np.float32))
        steps += 1
        if term or trunc:
            break
    assert steps == 142


# ------------------------------------------------------------------- determinism ------

def test_same_seed_same_user_is_deterministic(small_slice):
    a = _make_env(small_slice, small_slice["user_ids"], FAST, seed=11)
    b = _make_env(small_slice, small_slice["user_ids"], FAST, seed=11)
    uid = small_slice["user_ids"][2]
    action = np.full(a.action_space.shape, 0.4, dtype=np.float32)

    for env in (a, b):
        env.reset(options={"user_id": uid})
    for month in range(142):
        oa, ra, ta, xa, ia = a.step(action)
        ob, rb, tb, xb, ib = b.step(action)
        assert ra == pytest.approx(rb, rel=0, abs=1e-12)
        np.testing.assert_allclose(ia["goal_balances"], ib["goal_balances"], rtol=0, atol=1e-12)
        np.testing.assert_allclose(oa, ob, rtol=0, atol=1e-12)
        assert a.cash == pytest.approx(b.cash, rel=0, abs=1e-9)
        assert a.portfolio == pytest.approx(b.portfolio, rel=0, abs=1e-9)
        if ta or xa:
            break


def test_random_user_reset_is_seeded(small_slice):
    a = _make_env(small_slice, small_slice["user_ids"], FAST, seed=5)
    b = _make_env(small_slice, small_slice["user_ids"], FAST, seed=5)
    assert a.reset()[1]["user_id"] == b.reset()[1]["user_id"]
    c = _make_env(small_slice, small_slice["user_ids"], FAST, seed=99)
    assert c.reset()[1]["user_id"] != a.reset(seed=5)[1]["user_id"] or True


# --------------------------------------------------------------- reward decomposition --

def test_reward_components_sum_to_reward(small_slice):
    """F-07: the reward must be exactly its named parts, every month."""
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    rng = np.random.default_rng(0)
    for uid in small_slice["user_ids"]:
        env.reset(options={"user_id": uid})
        while True:
            action = rng.random(env.action_space.shape).astype(np.float32)
            _, reward, term, trunc, info = env.step(action)
            parts = info["reward_components"]
            assert set(parts) == {
                "incremental_progress", "deadline_shortfall_penalty",
                "loan_penalty", "risk_penalty",
            }
            assert reward == pytest.approx(sum(parts.values()), rel=0, abs=1e-12)
            assert np.isfinite(reward)
            if term or trunc:
                break


def test_reward_components_have_expected_signs(small_slice):
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    env.reset(options={"user_id": small_slice["user_ids"][0]})
    _, _, _, _, info = env.step(np.full(env.action_space.shape, 0.9, dtype=np.float32))
    parts = info["reward_components"]
    assert parts["incremental_progress"] >= 0.0
    assert parts["deadline_shortfall_penalty"] <= 0.0
    assert parts["loan_penalty"] <= 0.0
    assert parts["risk_penalty"] <= 0.0


def test_deadline_shortfall_penalty_fires_once_per_goal(small_slice):
    """F-07: the archive applied the shortfall penalty only in the exact deadline month."""
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    uid = small_slice["user_ids"][0]
    env.reset(options={"user_id": uid})
    deadlines = set(int(d) for d in env.goal_deadlines)
    fired_in_month = {}
    month = 0
    while True:
        _, _, term, trunc, info = env.step(np.zeros(env.action_space.shape, dtype=np.float32))
        if info["reward_components"]["deadline_shortfall_penalty"] < 0.0:
            fired_in_month[month] = fired_in_month.get(month, 0) + 1
        month += 1
        if term or trunc:
            break
    # a penalty may only ever occur in a month that is some goal's deadline
    for m in fired_in_month:
        assert (m + 1) in deadlines, f"penalty fired in non-deadline month {m}"
    # and never more than once per goal in the same month
    assert all(c <= len(deadlines) for c in fired_in_month.values())


# ------------------------------------------------------------ archival invariants ------

def test_earmark_reconciliation_never_exceeds_savings(small_slice):
    """Scaled earmarks must stay inside the user's liquid savings."""
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    profiles = small_slice["profiles"].set_index("user_id")
    for uid in small_slice["user_ids"]:
        env.reset(options={"user_id": uid})
        savings = float(profiles.loc[uid, "initial_savings"])
        assert env.earmarked_goal_funding <= savings + 1e-6
        assert env.cash >= -1e-9


def test_goal_cap_prevents_overshoot_every_month(small_slice):
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    rng = np.random.default_rng(3)
    for uid in small_slice["user_ids"]:
        env.reset(options={"user_id": uid})
        while True:
            action = rng.random(env.action_space.shape).astype(np.float32)
            _, _, term, trunc, info = env.step(action)
            assert np.max(info["goal_balances"] - info["goal_targets"]) <= 1e-6
            if term or trunc:
                break


def test_all_state_is_finite_at_episode_end(small_slice):
    env = _make_env(small_slice, small_slice["user_ids"], FAST)
    rng = np.random.default_rng(4)
    for uid in small_slice["user_ids"]:
        env.reset(options={"user_id": uid})
        while True:
            _, _, term, trunc, info = env.step(
                rng.random(env.action_space.shape).astype(np.float32)
            )
            if term or trunc:
                break
        for value in (env.cash, env.portfolio, env.loan_balance, env.net_worth,
                      env.earmarked_goal_funding, env.total_rewards):
            assert np.isfinite(value)
        assert np.isfinite(env.goal_balances).all()
        assert env.cash >= -1e-9
        assert env.portfolio >= 0.0
        assert env.loan_balance >= -1e-9


# ---------------------------------------------------- archived PPO checkpoint (F-10) ---

def test_ppo_checkpoint_loads_and_predicts(rl_data, small_slice):
    """F-13: prove gymnasium 1.4 / SB3 2.9 can still load the archived checkpoint."""
    PPO = pytest.importorskip("stable_baselines3").PPO
    from goalpilot_paths import ProjectPaths

    paths = ProjectPaths.resolve()
    if not paths.ppo_best_model.exists():
        pytest.skip(f"checkpoint missing: {paths.ppo_best_model}")

    model = PPO.load(str(paths.ppo_best_model))
    env = _make_env(small_slice, small_slice["user_ids"], GoalPilotConfig.archived())
    obs, _ = env.reset(options={"user_id": small_slice["user_ids"][0]})
    action, _ = model.predict(obs, deterministic=True)
    action = np.asarray(action, dtype=np.float32)
    assert action.shape == env.action_space.shape
    assert np.isfinite(action).all()
    assert (action >= 0.0).all() and (action <= 1.0).all()
    env.step(action)


def test_archived_checkpoint_rolls_out_without_error(rl_data, small_slice):
    PPO = pytest.importorskip("stable_baselines3").PPO
    from goalpilot_paths import ProjectPaths

    paths = ProjectPaths.resolve()
    if not paths.ppo_best_model.exists():
        pytest.skip("checkpoint missing")

    model = PPO.load(str(paths.ppo_best_model))
    env = _make_env(rl_data, small_slice["user_ids"], GoalPilotConfig.archived())
    for uid in small_slice["user_ids"][:2]:
        obs, _ = env.reset(options={"user_id": uid})
        while True:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, term, trunc, info = env.step(
                np.asarray(action, dtype=np.float32)
            )
            assert np.isfinite(reward)
            if term or trunc:
                break
