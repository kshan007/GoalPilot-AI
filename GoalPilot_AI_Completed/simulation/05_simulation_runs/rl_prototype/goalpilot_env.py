"""GoalPilot monthly multi-goal financial allocation environment (Gymnasium).

Research prototype. Not a financial-advice system.

Version 2 (2026-10-10) — audit remediation
==========================================
The archived version of this file is preserved verbatim as
``goalpilot_env.py.orig_20261010``. Everything the audit found is addressed through
configuration switches in :mod:`goalpilot_config`, and **every archived behaviour is
still reachable** by selecting ``GoalPilotConfig.archived()``.

Findings addressed
------------------
F-04 (S1) Contributions were counted twice: ``cash`` accumulated savings contributions
          while ``goal_balances`` *also* held them, and ``portfolio`` held the investments
          a second time. Any ``cash + portfolio + goal_balances`` aggregate was wrong.
          -> ``accounting_mode="ledger"`` keeps a real balance sheet. ``goal_balances``
          is now explicitly a **memo** account partitioning (cash + portfolio), and
          ``net_worth = cash + portfolio - loan_balance`` counts each rupee once.
          *Reward- and goal-funding-neutral.*

F-05 (S1) Loan proceeds created a goal asset but never reached an account, and EMI
          payments never left one. -> In ledger mode loan proceeds credit ``cash`` and
          the payment debits ``cash``, so ``net_worth`` moves only by
          (discretionary budget + investment gain - loan interest).

F-02 (S1) The action vector acted as a *magnitude*: ``budget_scale = min(1, budget/total)``
          never scales up, so any policy emitting below the saturation point silently
          under-funded goals, while above it the reward was flat (no gradient).
          -> ``action_mode="share"`` normalises the action to shares so the full
          available budget is always allocated.

F-01 (S1) Savings-only and Mixed-allocation produced *identical* goal funding because a
          rupee contributed was credited at face value whichever vehicle carried it.
          -> ``goal_credit_mode="growth_weighted"`` compounds each channel at its own
          rate up to the goal deadline, matching the LP. Mix now matters.

F-06 (S2) LP inflated goal targets by 3%/yr; the RL environment used nominal costs.
          -> ``target_basis="inflated"`` makes the environment use the LP basis.

F-07 (S2) Reward components were unvalidated and mutually mis-scaled. The reward
          *function is unchanged*; this version only exposes it decomposed via
          ``info["reward_components"]`` so it can be audited. See
          ``evaluation/reward_decomposition.py``.

F-10 (S3) Undertraining is a budget problem, not a code problem; nothing here changes
          the PPO hyper-parameters. ``config.seed`` makes runs reproducible.

F-12 (S3) No hard-coded paths; use :mod:`goalpilot_paths`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces

try:  # pragma: no cover - import shim so the module works both as a script and a package
    from goalpilot_config import (
        DEFAULT_CONFIG,
        ACTION_MODE_SHARE,
        ACTION_MODE_MIX,
        INVESTMENT_OVERFLOW_LEGACY,
        INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS,
        INVESTMENT_OVERFLOW_RETAIN_AS_CASH,
        ACCOUNTING_MODE_LEDGER,
        GOAL_CREDIT_GROWTH_WEIGHTED,
        GOAL_CREDIT_MARKET_WEIGHTED,
        REWARD_VERSION_A,
        REWARD_VERSION_ARCHIVED,
        REWARD_VERSION_B,
        GoalPilotConfig,
    )
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from goalpilot_config import (  # type: ignore
        DEFAULT_CONFIG,
        ACTION_MODE_SHARE,
        ACTION_MODE_MIX,
        INVESTMENT_OVERFLOW_LEGACY,
        INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS,
        INVESTMENT_OVERFLOW_RETAIN_AS_CASH,
        ACCOUNTING_MODE_LEDGER,
        GOAL_CREDIT_GROWTH_WEIGHTED,
        GOAL_CREDIT_MARKET_WEIGHTED,
        REWARD_VERSION_A,
        REWARD_VERSION_ARCHIVED,
        REWARD_VERSION_B,
        GoalPilotConfig,
    )


class GoalPilotEnv(gym.Env):
    """Monthly multi-goal financial allocation environment.

    This is a research prototype, not a financial-advice system.
    Inflation is applied to goal targets only when ``config.target_basis == "inflated"``.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(self, profiles, goals, market, user_ids=None, seed=None,
                 config: GoalPilotConfig | None = None):
        super().__init__()

        self.config: GoalPilotConfig = config if config is not None else DEFAULT_CONFIG
        if seed is not None and seed != self.config.seed:
            self.config = self.config.replace(seed=int(seed))

        self.profiles = profiles.copy().reset_index(drop=True)
        self.goals = goals.copy()
        self.market = market.sort_values("period").reset_index(drop=True).copy()

        self.profiles["user_id"] = self.profiles["user_id"].astype(str)
        self.goals["user_id"] = self.goals["user_id"].astype(str)
        self.market["period"] = pd.to_datetime(self.market["period"])

        self.user_ids = list(user_ids) if user_ids is not None else \
            self.profiles["user_id"].tolist()

        self.profile_map = self.profiles.set_index("user_id").to_dict("index")
        self.goal_map = {
            uid: group.sort_values("time_horizon_months").reset_index(drop=True)
            for uid, group in self.goals.groupby("user_id")
        }

        if not self.user_ids:
            raise ValueError("At least one user is required.")
        if not self.market["period"].is_monotonic_increasing:
            raise ValueError("Market periods must be sorted.")
        if self.market["period"].duplicated().any():
            raise ValueError("Market periods must be unique.")

        inferred_max_goals = int(self.goals.groupby("user_id").size().max())
        if self.config.n_goal_slots is not None:
            if self.config.n_goal_slots < inferred_max_goals:
                raise ValueError(
                    f"config.n_goal_slots={self.config.n_goal_slots} is smaller than the "
                    f"largest goal count in the supplied goals ({inferred_max_goals})."
                )
            self.max_goals = int(self.config.n_goal_slots)
        else:
            self.max_goals = inferred_max_goals
        self.max_steps = len(self.market)

        # Action per goal: savings allocation, investment allocation and loan request.
        self.action_space = spaces.Box(
            low=0.0, high=1.0, shape=(self.max_goals, 3), dtype=np.float32,
        )

        # Per-goal features: remaining amount, horizon, priority, criticality,
        # funding ratio and active flag.
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(12 + self.max_goals * 6,), dtype=np.float32,
        )

        self.rng = np.random.default_rng(self.config.seed)
        self.user_id = None
        self.user_goals = None
        self.month_index = 0
        self.cash = 0.0
        self.portfolio = 0.0
        self.loan_balance = 0.0
        self.loan_emi = 0.0
        self.loan_months_left = 0
        self.goal_balances = None
        self.goal_deadlines = None
        self.goal_targets = None
        self.total_rewards = 0.0
        # Ledger accumulators (audit trail)
        self.total_unallocated_surplus = 0.0
        self.total_interest_paid = 0.0
        self.total_investment_gain = 0.0
        self.cumulative_savings_contributions = 0.0
        self.cumulative_investment_contributions = 0.0
        self.cumulative_loan_principal = 0.0

    # ------------------------------------------------------------------ observation ---

    def _get_observation(self):
        p = self.profile_map[self.user_id]
        surplus = max(
            0.0,
            float(p["monthly_income"])
            - float(p["monthly_expenditure"])
            - float(p["monthly_emi"]),
        )

        market_row = self.market.iloc[self.month_index]
        obs = [
            np.clip(float(p["monthly_income"]) / 200000, 0, 1),
            np.clip(float(p["monthly_expenditure"]) / 200000, 0, 1),
            np.clip(float(p["monthly_emi"]) / 200000, 0, 1),
            np.clip(surplus / 100000, 0, 1),
            np.clip(self.cash / 2_000_000, 0, 1),
            np.clip(self.portfolio / 5_000_000, 0, 1),
            np.clip(self.loan_balance / 2_000_000, 0, 1),
            np.clip(float(p["investment_capacity_ratio"]), 0, 1),
            np.clip(float(p["risk_score"]), 0, 1),
            np.clip(self.month_index / max(1, self.max_steps - 1), 0, 1),
            np.clip((float(market_row["walr_monthly"]) / 100), 0, 1),
            np.clip((float(market_row["nifty_monthly_return"]) + 0.25) / 0.50, 0, 1),
        ]

        for j in range(self.max_goals):
            if j < len(self.goal_targets):
                target = max(float(self.goal_targets[j]), 1.0)
                remaining = max(0.0, target - self.goal_balances[j])
                horizon = max(0, self.goal_deadlines[j] - self.month_index)
                row = self.user_goals.iloc[j]
                obs.extend([
                    np.clip(remaining / 30_000_000, 0, 1),
                    np.clip(horizon / 240, 0, 1),
                    np.clip(float(row["priority"]) / 5, 0, 1),
                    np.clip(float(row["criticality"]) / 5, 0, 1),
                    np.clip(self.goal_balances[j] / target, 0, 1),
                    1.0,
                ])
            else:
                obs.extend([0.0] * 6)

        return np.asarray(obs, dtype=np.float32)

    # ------------------------------------------------------------------------ reset ---

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)

        options = options or {}
        requested_user = options.get("user_id")
        if requested_user is not None:
            requested_user = str(requested_user)
            if requested_user not in self.user_ids:
                raise ValueError(f"Unknown user_id: {requested_user}")
            self.user_id = requested_user
        else:
            self.user_id = self.rng.choice(self.user_ids)

        p = self.profile_map[self.user_id]
        self.user_goals = self.goal_map[self.user_id].copy().reset_index(drop=True)

        self.month_index = 0
        initial_savings = max(0.0, float(p["initial_savings"]))
        self.portfolio = max(0.0, float(p["initial_investment"]))
        self.loan_balance = 0.0
        self.loan_emi = 0.0
        self.loan_months_left = 0
        self.total_rewards = 0.0
        self.total_unallocated_surplus = 0.0
        self.total_interest_paid = 0.0
        self.total_investment_gain = 0.0
        self.cumulative_savings_contributions = 0.0
        self.cumulative_investment_contributions = 0.0
        self.cumulative_loan_principal = 0.0

        # ---- goal targets (F-06: target basis is now configurable) --------------------
        base_cost = self.user_goals["current_cost"].astype(float).to_numpy()
        if self.config.inflation_applies_to_goal_target:
            months = self.user_goals["time_horizon_months"].astype(float).to_numpy()
            self.goal_targets = base_cost * (1.0 + self.config.annual_inflation) ** (months / 12.0)
        else:
            self.goal_targets = base_cost
        self.goal_deadlines = self.user_goals["time_horizon_months"].astype(int).to_numpy()

        # ---- emergency reserve (LP parity; 0.0 reproduces archived behaviour) ---------
        essential = float(p["monthly_expenditure"])
        emergency_reserve = min(
            initial_savings,
            self.config.emergency_months * essential,
        )

        # ---- earmark reconciliation ---------------------------------------------------
        # Scale synthetic goal earmarks proportionally when they exceed savings that are
        # not already locked in the emergency reserve.
        original_funding = self.user_goals["existing_funding"].astype(float).to_numpy()
        total_earmarked = float(original_funding.sum(dtype="float64"))
        spendable_savings = max(0.0, initial_savings - emergency_reserve)
        funding_scale = (
            min(1.0, spendable_savings / total_earmarked)
            if total_earmarked > 0.0 else 1.0
        )
        self.goal_balances = original_funding * funding_scale
        # Market value of the investment money already earmarked to each goal. Only used by
        # goal_credit_mode == "market_weighted", where it is marked to market at the realised
        # NIFTY monthly return (finding R-03).
        self.goal_market_value = np.zeros(len(self.user_goals), dtype="float64")
        reconciled_earmarked = float(self.goal_balances.sum(dtype="float64"))
        # Unearmarked liquid cash. In ledger mode this is a real balance; in legacy mode
        # it is an accumulator (see module docstring).
        if self.config.accounting_mode == ACCOUNTING_MODE_LEDGER:
            # The emergency reserve is real household money, so it stays on the balance
            # sheet as restricted cash instead of disappearing from net worth (finding
            # R-02). It remains non-spendable, because goal allocations are drawn from
            # `surplus` only and never from `cash`.
            self.restricted_cash = emergency_reserve
            # The pre-existing goal earmark is *labelled* money, not spent money: it stays
            # inside cash, so earmarking neither creates nor destroys an asset (finding
            # R-11). `goal_balances` is therefore a pure memo partitioning cash + portfolio,
            # which is exactly what makes it safe never to add it to net worth again.
            # The reserve is likewise inside `cash`, reported separately as restricted.
            self.cash = max(0.0, initial_savings)
        else:
            self.restricted_cash = 0.0
            self.cash = max(
                0.0, initial_savings - reconciled_earmarked - emergency_reserve
            )
        self.emergency_reserve = emergency_reserve
        self.initial_net_worth = (
            self.cash + float(self.portfolio) - float(self.loan_balance)
        )

        return self._get_observation(), {
            "user_id": self.user_id,
            "goal_count": len(self.user_goals),
            "accounting_mode": self.config.accounting_mode,
            "action_mode": self.config.action_mode,
            "goal_credit_mode": self.config.goal_credit_mode,
            "target_basis": self.config.target_basis,
            "emergency_reserve": emergency_reserve,
            "restricted_cash": self.restricted_cash,
            "initial_net_worth": self.initial_net_worth,
        }

    # ------------------------------------------------------------------- allocation ---

    @staticmethod
    def _empty_overflow() -> dict:
        """Zero-valued overflow breakdown, for months with no capacity overflow."""
        return {
            "invest_requested": 0.0,
            "invest_actual": 0.0,
            "overflow": 0.0,
            "redirected_to_savings": 0.0,
            "retained_as_cash": 0.0,
        }

    def _settle_investment_overflow(self, savings_alloc, w_sav, overflow, n_goals,
                                    remaining_need):
        """Decide the fate of investment demand that exceeds the user's capacity.

        ``legacy`` (default) reproduces the historical behaviour, which is *mode dependent*:
        ``share`` returns the excess to the savings channel (proportional to the savings
        weights, or equally when there are none) and ``mix`` leaves it unallocated.
        ``retain_as_cash`` leaves the excess liquid and **uncredited** to any goal.
        ``redirect_to_savings`` reallocates it as **savings** to goals with remaining need, in
        proportion to that need; any part that no goal can absorb stays as cash.

        Returns ``(savings_alloc, redirected, retained)``. Redirected money is added to the
        savings channel only, so it is credited under the savings conventions and can never be
        double counted as an investment.
        """
        if overflow <= 0.0:
            return savings_alloc, 0.0, 0.0

        policy = self.config.investment_overflow_policy
        if policy == INVESTMENT_OVERFLOW_RETAIN_AS_CASH:
            return savings_alloc, 0.0, overflow
        if (policy == INVESTMENT_OVERFLOW_LEGACY
                and self.config.action_mode == ACTION_MODE_MIX):
            # historical `mix` behaviour: the excess simply stays unallocated
            return savings_alloc, 0.0, overflow
        if policy == INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS:
            if remaining_need is None:
                need = np.zeros(n_goals, dtype="float64")
            else:
                need = np.maximum(0.0, np.asarray(remaining_need, dtype="float64"))
            need_total = float(need.sum(dtype="float64"))
            if need_total <= 1e-12:
                # no eligible goal remains: retain the whole remainder as cash
                return savings_alloc, 0.0, overflow
            grant = np.minimum(overflow * (need / need_total), need)
            moved = float(grant.sum(dtype="float64"))
            return savings_alloc + grant, moved, overflow - moved

        # historical `share` behaviour
        if w_sav.sum() > 1e-12:
            savings_alloc = savings_alloc + w_sav / w_sav.sum() * overflow
        else:
            savings_alloc = savings_alloc + np.full(n_goals, overflow / n_goals)
        return savings_alloc, overflow, 0.0

    def _allocate(self, action, available_after_existing_loan, invest_cap, n_goals,
                  remaining_need=None):
        """Turn the action into rupee allocations.

        ``magnitude`` (archived): the action is an absolute fraction of the budget and
        ``budget_scale`` can only ever scale *down*.
        ``share``: the 2n savings/investment weights are normalised to shares, so the
        whole available budget is allocated whenever any weight is positive.
        ``mix``: as ``share``, but investment demand above the capacity limit is left
        unallocated instead of being relabelled as savings, so the requested mix is
        observable (finding R-12). Returns the unallocated amount as a third value; the
        other modes return 0.0 for it.
        """
        w_sav = action[:n_goals, 0].astype("float64")
        w_inv = action[:n_goals, 1].astype("float64")

        if self.config.action_mode == ACTION_MODE_SHARE:
            combined = np.concatenate([w_sav, w_inv])
            total = float(combined.sum())
            if total <= 1e-12:
                # An all-zero action stays a genuine no-op; the "No action" baseline
                # must not be silently converted into a full-budget allocation.
                zero = np.zeros(n_goals, dtype="float64")
                return zero, zero.copy(), self._empty_overflow()

            shares = combined / total
            savings_alloc = shares[:n_goals] * available_after_existing_loan
            invest_alloc = shares[n_goals:] * available_after_existing_loan

            # Investment capacity caps the invested portion. This cap is enforced even when
            # capacity is exactly zero, so a user with no investment capacity cannot invest.
            # Under the default `legacy` policy the excess stays liquid as savings, exactly as
            # it always has; the opt-in policies decide differently (see
            # `_settle_investment_overflow`).
            invest_requested = float(invest_alloc.sum())
            if invest_requested > invest_cap:
                overflow = invest_requested - invest_cap
                if invest_requested > 1e-12:
                    invest_alloc = invest_alloc * (invest_cap / invest_requested)
                else:
                    invest_alloc = np.zeros(n_goals, dtype="float64")
                savings_alloc, redirected, retained = self._settle_investment_overflow(
                    savings_alloc, w_sav, overflow, n_goals, remaining_need)
            else:
                overflow, redirected, retained = 0.0, 0.0, 0.0
            return savings_alloc, invest_alloc, {
                "invest_requested": invest_requested,
                "invest_actual": float(invest_alloc.sum(dtype="float64")),
                "overflow": overflow,
                "redirected_to_savings": redirected,
                "retained_as_cash": retained,
            }

        if self.config.action_mode == ACTION_MODE_MIX:
            combined = np.concatenate([w_sav, w_inv])
            total = float(combined.sum())
            if total <= 1e-12:
                zero = np.zeros(n_goals, dtype="float64")
                return zero, zero.copy(), self._empty_overflow()

            shares = combined / total
            savings_alloc = shares[:n_goals] * available_after_existing_loan
            invest_alloc = shares[n_goals:] * available_after_existing_loan

            # Investment demand above the capacity limit is genuinely uninvestable. Unlike
            # `share` mode it is NOT relabelled as savings for the goals: it stays
            # unallocated and shows up in `unallocated_surplus`. This single difference is
            # what makes the requested mix observable, so an investment-only request no
            # longer silently becomes a savings-heavy policy (finding R-12).
            invest_requested = float(invest_alloc.sum())
            if invest_requested > invest_cap:
                overflow = invest_requested - invest_cap
                if invest_requested > 1e-12:
                    invest_alloc = invest_alloc * (invest_cap / invest_requested)
                else:
                    invest_alloc = np.zeros(n_goals, dtype="float64")
                savings_alloc, redirected, retained = self._settle_investment_overflow(
                    savings_alloc, w_sav, overflow, n_goals, remaining_need)
            else:
                overflow, redirected, retained = 0.0, 0.0, 0.0
            return savings_alloc, invest_alloc, {
                "invest_requested": invest_requested,
                "invest_actual": float(invest_alloc.sum(dtype="float64")),
                "overflow": overflow,
                "redirected_to_savings": redirected,
                "retained_as_cash": retained,
            }

        # ---- archived magnitude semantics ---------------------------------------------
        raw_savings = w_sav * available_after_existing_loan
        raw_investments = w_inv * invest_cap
        total_raw = float(raw_savings.sum() + raw_investments.sum())
        budget_scale = min(
            1.0,
            available_after_existing_loan / total_raw if total_raw > 0 else 1.0,
        )
        return (raw_savings * budget_scale, raw_investments * budget_scale,
                self._empty_overflow())

    def _credit_goals(self, savings_alloc, invest_alloc, n_goals):
        """Value of each channel for goal-funding purposes.

        ``face_value`` (archived): 1 rupee contributed = 1 rupee of goal funding.
        ``growth_weighted``: compound each channel at its own rate to the goal deadline,
        matching how the LP values contributions. The compounded growth is a *projection*
        and is therefore booked even though it has not been earned (finding R-03).
        ``market_weighted``: a new contribution is also worth its face value today — the
        realised revaluation of money already earmarked is added separately in ``step``,
        after the per-goal cap, because it has already been earned.
        """
        if self.config.goal_credit_mode != GOAL_CREDIT_GROWTH_WEIGHTED:
            return savings_alloc, invest_alloc

        cred_sav = np.empty(n_goals, dtype="float64")
        cred_inv = np.empty(n_goals, dtype="float64")
        for j in range(n_goals):
            months_left = max(0, int(self.goal_deadlines[j]) - int(self.month_index))
            years = months_left / 12.0
            cred_sav[j] = (1.0 + self.config.annual_savings_return) ** years
            cred_inv[j] = (1.0 + self.config.investment_return_assumption) ** years
        return savings_alloc * cred_sav, invest_alloc * cred_inv

    # ------------------------------------------------------------------------- step ---

    def step(self, action):
        action = np.asarray(action, dtype=np.float32)
        if action.shape != self.action_space.shape:
            raise ValueError(f"Expected action shape {self.action_space.shape}, got {action.shape}")
        if not np.isfinite(action).all():
            raise ValueError("Action contains non-finite values.")

        action = np.clip(action, 0, 1)
        p = self.profile_map[self.user_id]
        m = self.market.iloc[self.month_index]
        n_goals = len(self.user_goals)

        # ---- mark the goal-earmarked investment book to market ('market_weighted', R-03) --
        # Realised only: the same monthly market return the portfolio itself earns is applied
        # to the money already earmarked to each goal. No projected return is booked, so goal
        # funding can never exceed cash + portfolio.
        goal_market_gain = np.zeros(n_goals, dtype="float64")
        market_return = float(m["nifty_monthly_return"])
        if self.config.goal_credit_mode == GOAL_CREDIT_MARKET_WEIGHTED:
            goal_market_gain = self.goal_market_value * market_return
            self.goal_market_value = self.goal_market_value + goal_market_gain

        income = float(p["monthly_income"])
        expenses = float(p["monthly_expenditure"])
        existing_emi = float(p["monthly_emi"])
        surplus = max(0.0, income - expenses - existing_emi)

        # ---- payment due on the environment's own outstanding loan ---------------------
        if self.loan_months_left > 0 and self.loan_balance > 1e-6:
            annual_rate_existing = float(m["walr_monthly"]) / 100.0
            monthly_rate_existing = (1.0 + annual_rate_existing) ** (1.0 / 12.0) - 1.0
            interest_due_before_allocation = self.loan_balance * monthly_rate_existing
            scheduled_emi = max(0.0, self.loan_emi)
            payoff_amount = self.loan_balance + interest_due_before_allocation
            current_emi_due = min(scheduled_emi, payoff_amount, surplus)
        else:
            current_emi_due = 0.0
            self.loan_balance = 0.0
            self.loan_emi = 0.0
            self.loan_months_left = 0

        available_after_existing_loan = max(0.0, surplus - current_emi_due)
        invest_cap = available_after_existing_loan * float(p["investment_capacity_ratio"])

        # ---- allocate the shared monthly budget across goals --------------------------
        remaining_need_for_overflow = np.maximum(
            0.0, self.goal_targets.astype("float64") - self.goal_balances
        )
        (
            savings_alloc,
            invest_alloc,
            overflow_info,
        ) = self._allocate(action, available_after_existing_loan, invest_cap, n_goals,
                           remaining_need_for_overflow)
        unallocated_from_investment_cap = overflow_info["retained_as_cash"]

        # ---- do not allocate beyond each goal's remaining target ----------------------
        # For growth_weighted crediting the cap applies to *credited* value, so we
        # translate back to contributions before scaling.
        remaining_by_goal = np.maximum(
            0.0,
            self.goal_targets.astype("float64") - self.goal_balances.astype("float64"),
        )
        credited_sav, credited_inv = self._credit_goals(savings_alloc, invest_alloc, n_goals)
        requested_by_goal = credited_sav + credited_inv
        goal_cap_scale = np.ones_like(requested_by_goal, dtype="float64")
        positive_requests = requested_by_goal > 0.0
        goal_cap_scale[positive_requests] = np.minimum(
            1.0,
            remaining_by_goal[positive_requests] / requested_by_goal[positive_requests],
        )
        pre_cap_savings_total = float(savings_alloc.sum(dtype="float64"))
        pre_cap_invest_total = float(invest_alloc.sum(dtype="float64"))
        savings_alloc = savings_alloc * goal_cap_scale
        invest_alloc = invest_alloc * goal_cap_scale
        credited_sav = credited_sav * goal_cap_scale
        credited_inv = credited_inv * goal_cap_scale

        # ---- reallocate the budget released by the per-goal cap (finding R-13) ---------
        # The cap leaves `released` rupees unallocated and they are discarded, which measurably
        # destroys 26-51% of the monthly budget. When `reallocate_capped_budget` is set, that
        # money is given to goals that still need it, in proportion to the need, keeping the
        # channel split of the surviving allocation and the investment-capacity limit. Off by
        # default, so behaviour without the flag is byte-identical to before.
        released = (
            pre_cap_savings_total - float(savings_alloc.sum(dtype="float64"))
            + pre_cap_invest_total - float(invest_alloc.sum(dtype="float64"))
        )
        reallocated_from_cap = 0.0
        if self.config.reallocate_capped_budget and released > 1e-9:
            remaining_after_cap = np.maximum(
                0.0, remaining_by_goal - (credited_sav + credited_inv)
            )
            allocated_total = float(
                savings_alloc.sum(dtype="float64") + invest_alloc.sum(dtype="float64")
            )
            invest_share = (
                float(invest_alloc.sum(dtype="float64")) / allocated_total
                if allocated_total > 1e-9 else 0.0
            )
            # keep each channel's own credit convention (face value, or compounded growth)
            with np.errstate(divide="ignore", invalid="ignore"):
                mult_sav = np.where(
                    savings_alloc > 1e-12,
                    credited_sav / np.maximum(savings_alloc, 1e-12), 1.0,
                )
                mult_inv = np.where(
                    invest_alloc > 1e-12,
                    credited_inv / np.maximum(invest_alloc, 1e-12), 1.0,
                )
            pool = released
            for _ in range(4):
                need_total = float(remaining_after_cap.sum(dtype="float64"))
                if pool <= 1e-9 or need_total <= 1e-9:
                    break
                weights = remaining_after_cap / need_total
                grant = np.minimum(pool * weights, remaining_after_cap)
                room = max(0.0, invest_cap - float(invest_alloc.sum(dtype="float64")))
                grant_inv = np.minimum(grant * invest_share, room)
                grant_sav = grant - grant_inv
                savings_alloc = savings_alloc + grant_sav
                invest_alloc = invest_alloc + grant_inv
                credited_grant = grant_sav * mult_sav + grant_inv * mult_inv
                credited_sav = credited_sav + grant_sav * mult_sav
                credited_inv = credited_inv + grant_inv * mult_inv
                remaining_after_cap = np.maximum(
                    0.0, remaining_after_cap - credited_grant
                )
                moved = float((grant_sav + grant_inv).sum(dtype="float64"))
                pool -= moved
                reallocated_from_cap += moved

        # ---- originate a new loan if the EMI fits the remaining surplus ---------------
        new_loan = 0.0
        new_emi = 0.0
        new_loan_goal_idx = -1
        tenure = self.config.loan_tenure_months
        if self.loan_months_left == 0 and available_after_existing_loan > 0:
            goal_idx = int(np.argmax(action[:n_goals, 2]))
            new_loan_goal_idx = goal_idx
            requested_fraction = float(action[goal_idx, 2])
            annual_rate = float(m["walr_monthly"]) / 100.0
            monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
            emi_factor = (
                monthly_rate * (1 + monthly_rate) ** tenure
                / ((1 + monthly_rate) ** tenure - 1)
            )
            emi_budget = max(
                0.0,
                min(
                    available_after_existing_loan
                    - float(savings_alloc.sum()) - float(invest_alloc.sum()),
                    income * self.config.emi_income_ratio_cap - existing_emi - self.loan_emi,
                ),
            )
            new_emi = min(emi_budget, requested_fraction * emi_budget)
            new_loan = new_emi / emi_factor if emi_factor > 0 else 0.0
            new_loan = min(new_loan, self.config.max_new_loan)
            remaining_goal_need = max(
                0.0,
                float(self.goal_targets[goal_idx])
                - float(self.goal_balances[goal_idx])
                - float(credited_sav[goal_idx])
                - float(credited_inv[goal_idx]),
            )
            new_loan = min(new_loan, remaining_goal_need)
            new_emi = new_loan * emi_factor

            if new_emi > emi_budget + 1e-5:
                new_loan = emi_budget / emi_factor
                new_emi = new_loan * emi_factor

        # ---- enforce the cash-flow budget before touching state -----------------------
        discretionary_budget = max(0.0, surplus - current_emi_due - new_emi)
        discretionary_total = float(savings_alloc.sum(dtype="float64")
                                   + invest_alloc.sum(dtype="float64"))
        # Product of every re-scaling applied below. Exposed on `budget_audit` so that a
        # silent clamp can never go unnoticed (finding R-05).
        guard_scale = 1.0

        if discretionary_total > discretionary_budget and discretionary_total > 0.0:
            guard_scale = discretionary_budget / discretionary_total
            savings_alloc = savings_alloc * guard_scale
            invest_alloc = invest_alloc * guard_scale
            credited_sav = credited_sav * guard_scale
            credited_inv = credited_inv * guard_scale

            guarded_total = float(savings_alloc.sum(dtype="float64")
                                  + invest_alloc.sum(dtype="float64"))
            if guarded_total > discretionary_budget and guarded_total > 0.0:
                final_scale = discretionary_budget / guarded_total
                guard_scale *= final_scale
                savings_alloc = savings_alloc * final_scale
                invest_alloc = invest_alloc * final_scale
                credited_sav = credited_sav * final_scale
                credited_inv = credited_inv * final_scale

        # ---- loan amount actually applied to the selected goal ------------------------
        loan_goal_contribution = 0.0
        if new_loan > 0.0 and new_loan_goal_idx >= 0:
            remaining_after_contributions = max(
                0.0,
                float(self.goal_targets[new_loan_goal_idx])
                - float(self.goal_balances[new_loan_goal_idx])
                - float(credited_sav[new_loan_goal_idx])
                - float(credited_inv[new_loan_goal_idx]),
            )
            loan_goal_contribution = min(float(new_loan), remaining_after_contributions)

        # ---- apply the monthly portfolio return and cash movements -------------------
        market_return = float(m["nifty_monthly_return"])
        previous_portfolio = self.portfolio
        previous_net_worth = self.net_worth

        invest_total = float(invest_alloc.sum(dtype="float64"))
        savings_total = float(savings_alloc.sum(dtype="float64"))
        self.portfolio = max(
            0.0, self.portfolio * (1 + market_return) + invest_total,
        )
        investment_gain = self.portfolio - previous_portfolio - invest_total
        self.total_investment_gain += investment_gain

        # ---- repay the outstanding loan (interest-first amortisation) -----------------
        interest_due = 0.0            # accrued this month
        interest_paid_cash = 0.0      # actually paid in cash this month
        interest_shortfall = 0.0      # accrued but not paid (see R-04)
        actual_payment = 0.0
        principal_paid = 0.0
        residual_due = 0.0            # principal left when the tenure runs out (R-01)
        residual_written_off = 0.0
        emi_due = current_emi_due
        if emi_due > 0.0:
            annual_rate_existing = float(m["walr_monthly"]) / 100.0
            monthly_rate_existing = (1.0 + annual_rate_existing) ** (1.0 / 12.0) - 1.0
            interest_due = self.loan_balance * monthly_rate_existing
            payment_due = self.loan_balance + interest_due
            actual_payment = min(emi_due, payment_due)
            interest_paid_cash = min(actual_payment, interest_due)
            interest_shortfall = max(0.0, interest_due - interest_paid_cash)
            principal_paid = max(0.0, actual_payment - interest_due)
            self.loan_balance = max(0.0, self.loan_balance - principal_paid)
            if interest_shortfall > 0.0 and self.config.accounting_mode == ACCOUNTING_MODE_LEDGER:
                # Accrued interest that was not paid must stay on the books rather than
                # being silently forgiven (finding R-04). In practice the affordability
                # cap makes this structurally zero; it is capitalised so that the audit
                # trail stays honest if it ever is not.
                self.loan_balance += interest_shortfall
            self.loan_months_left = max(0, self.loan_months_left - 1)

            if self.loan_balance <= 1e-6:
                self.loan_balance = 0.0
                self.loan_emi = 0.0
                self.loan_months_left = 0
            elif self.loan_months_left == 0:
                # Tenure exhausted while principal is still outstanding. The level EMI is
                # fixed at origination while interest accrues at each month's actual rate,
                # so a small residual is possible (finding R-01).
                if self.config.accounting_mode == ACCOUNTING_MODE_LEDGER:
                    # Never erase the liability: settle it in cash below, or carry it.
                    residual_due = self.loan_balance
                else:
                    # Archived behaviour: implicit write-off, preserved for exact parity.
                    residual_written_off = self.loan_balance
                    self.loan_balance = 0.0
                    self.loan_emi = 0.0
                    self.loan_months_left = 0

        self.total_interest_paid += interest_paid_cash

        # ---- originate the new loan ---------------------------------------------------
        if new_loan > 0:
            self.loan_balance = float(new_loan)
            self.loan_emi = float(new_emi)
            self.loan_months_left = int(tenure)

        monthly_loan_commitment = emi_due + float(new_emi)

        # ---- cash movement ------------------------------------------------------------
        unallocated_surplus = max(0.0, discretionary_budget - discretionary_total)
        self.total_unallocated_surplus += unallocated_surplus
        self.cumulative_savings_contributions += savings_total
        self.cumulative_investment_contributions += invest_total
        self.cumulative_loan_principal += float(new_loan)

        cash_floor_active = False
        residual_settled_cash = 0.0
        residual_carried = 0.0
        if self.config.accounting_mode == ACCOUNTING_MODE_LEDGER:
            # Real balance sheet. Cash movements for the month are:
            #   + surplus                     (already net of expenses and the profile's own EMI)
            #   - actual_payment              (this month's payment on the env's own loan)
            #   - invest_total                (money actually converted into the portfolio)
            #   + new_loan                    (proceeds of a freshly originated loan)
            #   - residual_settled_cash       (settlement of a residual lien, finding R-01)
            # Savings contributions and `unallocated_surplus` are *earmarks*, not spending:
            # the money stays in cash and `goal_balances` merely labels it. That is why
            # `goal_balances` is a memo account and must never be added to net worth.
            # The new loan's EMI is reserved inside `discretionary_budget` but is not paid
            # until the following month, so it is not a cash movement here.
            cash_unfloored = (
                self.cash + surplus - actual_payment - invest_total + float(new_loan)
            )
            # Exposed so that a silently-triggered floor is visible in the audit trail.
            cash_floor_active = cash_unfloored < 0.0
            self.cash = max(0.0, cash_unfloored)

            if residual_due > 0.0:
                # Explicit settlement of the residual lien left at tenure expiry: cash out
                # and liability down by the same amount, so net worth is unchanged.
                residual_settled_cash = min(residual_due, self.cash)
                self.cash -= residual_settled_cash
                outstanding = residual_due - residual_settled_cash
                if outstanding > 1e-6:
                    # Not enough cash to discharge it: the liability stays on the books and
                    # keeps being serviced next month instead of disappearing.
                    self.loan_balance = outstanding
                    self.loan_months_left = 1
                    residual_carried = outstanding
                else:
                    self.loan_balance = 0.0
                    self.loan_emi = 0.0
                    self.loan_months_left = 0
        else:
            # Archived accumulator: contributions pile up in `cash` *and* in
            # `goal_balances`, and payments never leave an account.
            self.cash += savings_total

        # ---- credit goal balances (memo account) --------------------------------------
        contribution = credited_sav + credited_inv
        if self.config.goal_credit_mode == GOAL_CREDIT_MARKET_WEIGHTED:
            # Realised revaluation of the money already earmarked to each goal. It is added
            # outside the per-goal cap because it has already been earned rather than
            # requested, and the new investment money is added to the marked book.
            contribution = contribution + goal_market_gain
            self.goal_market_value = self.goal_market_value + invest_alloc
        if loan_goal_contribution > 0.0:
            contribution[new_loan_goal_idx] += loan_goal_contribution
        if self.config.reallocate_capped_budget:
            # Part of the R-13 package: never credit a goal past its target. The monthly market
            # gain is credited outside the per-goal cap, so without this a funded goal can drift
            # above its target. Clamping only the *credit* is correct: the money already moved
            # into cash/portfolio stays there as unattributed wealth, so the memo invariant
            # `sum(goal_balances) <= cash + portfolio` is preserved.
            headroom = np.maximum(
                0.0, self.goal_targets.astype("float64") - self.goal_balances
            )
            contribution = np.minimum(contribution, headroom)
        previous_goal_balances = self.goal_balances.copy()
        for j, amount in enumerate(contribution):
            self.goal_balances[j] += float(amount)

        # ---- reward (archived version byte-for-byte; candidates are separate) ---------
        reward = 0.0
        reward_components = {
            "incremental_progress": 0.0,
            "deadline_shortfall_penalty": 0.0,
            "loan_penalty": 0.0,
            "risk_penalty": 0.0,
        }
        if self.config.reward_version != REWARD_VERSION_ARCHIVED:
            # Candidate-only terms. They are added only when a candidate version is selected,
            # so the archived audit surface stays bit-identical to the historical one.
            reward_components.update({
                "wealth_delta": 0.0,
                "terminal_net_worth": 0.0,
                "terminal_goal_achievement": 0.0,
            })
        budget_base = max(surplus, 1.0)

        if self.config.reward_version == REWARD_VERSION_ARCHIVED:
            for j in range(n_goals):
                target = max(1.0, float(self.goal_targets[j]))
                previous_ratio = min(1.0, max(0.0, previous_goal_balances[j] / target))
                current_ratio = min(1.0, max(0.0, self.goal_balances[j] / target))
                priority = float(self.user_goals.iloc[j]["priority"])
                criticality = float(self.user_goals.iloc[j]["criticality"])

                progress_term = 2.0 * max(0.0, current_ratio - previous_ratio) * priority / 5.0
                reward_components["incremental_progress"] += progress_term
                reward += progress_term

                if self.month_index + 1 == self.goal_deadlines[j]:
                    shortfall_ratio = max(0.0, (target - self.goal_balances[j]) / target)
                    penalty = 5.0 * shortfall_ratio * criticality / 5.0
                    reward_components["deadline_shortfall_penalty"] -= penalty
                    reward -= penalty

            loan_penalty = 0.00001 * new_loan
            reward_components["loan_penalty"] = -loan_penalty
            reward -= loan_penalty

            risk_score = float(p["risk_score"])
            risk_penalty = max(0.0, abs(market_return) - risk_score * 0.05) * (
                self.portfolio / 100000.0
            )
            reward_components["risk_penalty"] = -risk_penalty
            reward -= risk_penalty

        else:
            # ---- candidate rewards (Phase D). See REWARD_DESIGN_RATIONALE.md -------------
            if self.config.reward_version == REWARD_VERSION_A:
                for j in range(n_goals):
                    target = max(1.0, float(self.goal_targets[j]))
                    previous_ratio = min(1.0, max(0.0, previous_goal_balances[j] / target))
                    current_ratio = min(1.0, max(0.0, self.goal_balances[j] / target))
                    priority = float(self.user_goals.iloc[j]["priority"])
                    criticality = float(self.user_goals.iloc[j]["criticality"])

                    # ratio-normalised, so a large and a small goal are equally tractable
                    progress_term = 2.0 * max(0.0, current_ratio - previous_ratio) * priority / 5.0
                    reward_components["incremental_progress"] += progress_term
                    reward += progress_term

                    # graduated shortfall: ramps to full weight in the deadline month
                    months_left = int(self.goal_deadlines[j]) - int(self.month_index)
                    window = max(1, int(self.config.shortfall_window_months))
                    if 0 < months_left <= window:
                        ramp = 1.0 - (months_left - 1) / float(window)
                        penalty = 5.0 * ramp * max(0.0, 1.0 - current_ratio) * criticality / 5.0
                        reward_components["deadline_shortfall_penalty"] -= penalty
                        reward -= penalty

                # debt service priced on the month's interest cost, relative to the budget
                loan_cost = self.config.loan_cost_weight * (interest_due / budget_base)
                reward_components["loan_penalty"] = -loan_cost
                reward -= loan_cost

                # downside-only charge on the money actually exposed this month
                downside = (
                    self.config.downside_risk_weight
                    * max(0.0, -market_return)
                    * (invest_total / budget_base)
                )
                reward_components["risk_penalty"] = -downside
                reward -= downside

                if self.month_index + 1 >= self.max_steps:
                    terminal = self.config.terminal_net_worth_weight * (
                        (self.net_worth - self.initial_net_worth)
                        / max(abs(self.initial_net_worth), 1.0)
                    )
                    reward_components["terminal_net_worth"] = terminal
                    reward += terminal

            elif self.config.reward_version == REWARD_VERSION_B:
                # one interpretable realised-wealth term: it already nets interest paid and
                # market outcomes, so debt and risk need no separate penalty
                wealth = self.config.wealth_delta_weight * (
                    (self.net_worth - previous_net_worth) / budget_base
                )
                reward_components["wealth_delta"] = wealth
                reward += wealth

                for j in range(n_goals):
                    target = max(1.0, float(self.goal_targets[j]))
                    current_ratio = min(1.0, max(0.0, self.goal_balances[j] / target))
                    criticality = float(self.user_goals.iloc[j]["criticality"])
                    months_left = int(self.goal_deadlines[j]) - int(self.month_index)
                    window = max(1, int(self.config.shortfall_window_months))
                    if 0 < months_left <= window:
                        ramp = 1.0 - (months_left - 1) / float(window)
                        penalty = 5.0 * ramp * max(0.0, 1.0 - current_ratio) * criticality / 5.0
                        reward_components["deadline_shortfall_penalty"] -= penalty
                        reward -= penalty

                if self.month_index + 1 >= self.max_steps:
                    achievement = float(np.mean([
                        min(1.0, self.goal_balances[j] / max(1.0, float(self.goal_targets[j])))
                        * float(self.user_goals.iloc[j]["priority"]) / 5.0
                        for j in range(n_goals)
                    ]))
                    terminal = self.config.terminal_achievement_weight * achievement
                    reward_components["terminal_goal_achievement"] = terminal
                    reward += terminal

        # ---- cash-flow invariant (kept from the archived version) ---------------------
        combined_commitment = savings_total + invest_total + monthly_loan_commitment
        if combined_commitment > surplus + 1e-4:
            raise RuntimeError(
                "Combined monthly cash-flow budget was exceeded. "
                f"month_index={self.month_index}, user_id={self.user_id}, "
                f"surplus={surplus:.6f}, savings={savings_total:.6f}, "
                f"investments={invest_total:.6f}, "
                f"monthly_loan_commitment={monthly_loan_commitment:.6f}, "
                f"new_emi={new_emi:.6f}, new_loan={new_loan:.6f}, "
                f"available_after_existing_loan={available_after_existing_loan:.6f}, "
                f"loan_months_left={self.loan_months_left}"
            )

        self.month_index += 1
        terminated = self.month_index >= self.max_steps
        truncated = False
        observation = (
            self._get_observation()
            if not terminated
            else np.zeros(self.observation_space.shape, dtype=np.float32)
        )
        self.total_rewards += reward

        # ---- audit trail ---------------------------------------------------------------
        net_worth = self.net_worth
        budget_audit = {
            "month": int(self.month_index - 1),
            "income": income,
            "expenses": expenses,
            "profile_existing_emi": existing_emi,
            "surplus": surplus,
            "env_loan_emi_paid": actual_payment,
            "new_loan_emi_committed": float(new_emi),
            "discretionary_budget": discretionary_budget,
            "savings_contribution": savings_total,
            "investment_contribution": invest_total,
            "unallocated_surplus": unallocated_surplus,
            "budget_check": (
                savings_total + invest_total + unallocated_surplus
                - discretionary_budget
            ),
            # ---- exposure of otherwise-invisible events (findings R-04, R-05) -------------
            "interest_accrued": interest_due,
            "interest_paid_cash": interest_paid_cash,
            "interest_shortfall": interest_shortfall,
            "guard_scale": guard_scale,
            "released_by_goal_cap": released,
            "unallocated_from_investment_cap": unallocated_from_investment_cap,
            # investment-cap overflow, recorded explicitly so nothing is implicit
            "invest_requested": overflow_info["invest_requested"],
            "invest_actual": overflow_info["invest_actual"],
            "invest_overflow": overflow_info["overflow"],
            "overflow_redirected_to_savings": overflow_info["redirected_to_savings"],
            "overflow_retained_as_cash": overflow_info["retained_as_cash"],
            "reallocated_from_cap": reallocated_from_cap,
            "cash_floor_active": cash_floor_active,
            "residual_settled_cash": residual_settled_cash,
            "residual_carried": residual_carried,
            "residual_written_off": residual_written_off,
            "net_worth": net_worth,
            "net_worth_change": net_worth - previous_net_worth,
            # Assets grow by the month's surplus, less accrual-basis loan interest, plus
            # market gains. Loan origination, principal repayment and the settlement of a
            # residual lien are all net-zero (asset up / liability up, then cash down /
            # liability down). Any unpaid accrued interest is capitalised, so `interest_due`
            # — not the cash figure — is the correct deduction on an accrual basis.
            "expected_net_worth_change": surplus + investment_gain - interest_due,
        }
        ledger = {
            "cash": float(self.cash),
            "portfolio": float(self.portfolio),
            "loan_balance": float(self.loan_balance),
            "goal_balances_total": float(self.goal_balances.sum(dtype="float64")),
            "net_worth": net_worth,
        }

        info = {
            # ---- keys present in the archived version (kept for compatibility) --------
            "user_id": self.user_id,
            "monthly_surplus": surplus,
            "savings_contribution": savings_total,
            "investment_contribution": invest_total,
            "new_loan_principal": float(new_loan),
            "new_loan_emi": float(new_emi),
            "active_loan_emi": float(self.loan_emi),
            "combined_monthly_commitment": combined_commitment,
            "portfolio_value": self.portfolio,
            "loan_balance": self.loan_balance,
            "goal_balances": self.goal_balances.copy(),
            "goal_targets": self.goal_targets.copy(),
            "portfolio_market_change": self.portfolio - previous_portfolio,
            # ---- new audit keys ------------------------------------------------------
            "unallocated_surplus": unallocated_surplus,
            # `interest_paid` is the cash interest actually paid this month; the accrual
            # figure is reported separately (finding R-04). The affordability cap makes
            # the two equal in every reachable configuration, which the ledger-integrity
            # tests assert rather than assume.
            "interest_paid": interest_paid_cash,
            "restricted_cash": float(self.restricted_cash),
            "goal_market_value": float(self.goal_market_value.sum(dtype="float64")),
            "interest_accrued": interest_due,
            "interest_shortfall": interest_shortfall,
            "residual_settled_cash": residual_settled_cash,
            "residual_carried": residual_carried,
            "residual_written_off": residual_written_off,
            "investment_gain": investment_gain,
            "net_worth": net_worth,
            "cash": float(self.cash),
            "reward_components": reward_components,
            "budget_audit": budget_audit,
            "ledger": ledger,
        }
        return observation, float(reward), terminated, truncated, info

    # ---------------------------------------------------------------------- helpers ---

    @property
    def net_worth(self) -> float:
        """Assets minus liabilities. Each rupee counted exactly once.

        In ``legacy`` accounting this is inflated because contributions sit in ``cash``
        *and* in ``goal_balances`` (finding F-04). Use ``accounting_mode="ledger"`` for a
        correct figure.
        """
        return float(self.cash) + float(self.portfolio) - float(self.loan_balance)

    @property
    def earmarked_goal_funding(self) -> float:
        """Memo total of funding earmarked to goals (subset of assets in ledger mode)."""
        return float(self.goal_balances.sum(dtype="float64"))

    def funding_ratio(self) -> float:
        targets = np.asarray(self.goal_targets, dtype=float)
        balances = np.asarray(self.goal_balances, dtype=float)
        return float(np.minimum(balances, targets).sum() / max(targets.sum(), 1.0))

    def goal_level_report(self) -> pd.DataFrame:
        return pd.DataFrame({
            "goal_id": self.user_goals["goal_id"].to_numpy(),
            "goal_name": self.user_goals["goal_name"].to_numpy(),
            "target": self.goal_targets,
            "funded": self.goal_balances,
            "funding_ratio": np.minimum(self.goal_balances, self.goal_targets)
            / np.maximum(self.goal_targets, 1e-9),
            "deadline_month": self.goal_deadlines,
        })

    def render(self):
        print({
            "user_id": self.user_id,
            "month_index": self.month_index,
            "cash": round(self.cash, 2),
            "portfolio": round(self.portfolio, 2),
            "loan_balance": round(self.loan_balance, 2),
            "net_worth": round(self.net_worth, 2),
            "earmarked_goal_funding": round(self.earmarked_goal_funding, 2),
            "total_rewards": round(self.total_rewards, 3),
        })
