"""Single source of truth for GoalPilot environment / LP assumptions.

Why this module exists
----------------------
The audit (docs/audit/AUDIT_REPORT.md, finding F-06) showed that the LP optimizer and
the Gymnasium RL environment were using *different* goal targets and *different*
assumptions, while their outputs were being compared side by side:

    LP  : future_goal_cost = current_cost * (1 + annual_inflation) ** (months / 12)
    RL  : goal_targets     = current_cost                      # nominal

This module centralises every such assumption so that both paths can be driven from one
configuration object, and so that a parity test can assert they agree.

Nothing here changes behaviour on its own: every default reproduces the archived
behaviour exactly, with one deliberate exception, `accounting_mode`, which defaults to
"ledger" because the legacy cash/loan ledger double-counted contributions
(findings F-04 and F-05). See `accounting_mode` below for the exact difference.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from typing import Any

# --------------------------------------------------------------------------------------
# Enumerations (kept as plain strings so they serialise cleanly into logs/JSON)
# --------------------------------------------------------------------------------------

ACTION_MODE_MAGNITUDE = "magnitude"
ACTION_MODE_SHARE = "share"
ACTION_MODE_MIX = "mix"
ACTION_MODES = (ACTION_MODE_MAGNITUDE, ACTION_MODE_SHARE, ACTION_MODE_MIX)

# What happens to investment demand that exceeds the user's investment capacity.
# `legacy` (default) reproduces the historical behaviour, which is *mode dependent*: `share`
#   returns the excess to the savings channel, `mix` leaves it unallocated. A concrete default
#   would silently change one of the two mappings, so the sentinel is required to preserve
#   every existing preset, published result and checkpoint.
# `retain_as_cash`     - the excess stays liquid cash and is NOT credited to any goal.
# `redirect_to_savings` - the excess is reallocated as SAVINGS to goals with remaining need,
#   in proportion to that need; anything left when no goal has need stays as cash.
INVESTMENT_OVERFLOW_LEGACY = "legacy"
INVESTMENT_OVERFLOW_RETAIN_AS_CASH = "retain_as_cash"
INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS = "redirect_to_savings"
INVESTMENT_OVERFLOW_POLICIES = (
    INVESTMENT_OVERFLOW_LEGACY,
    INVESTMENT_OVERFLOW_RETAIN_AS_CASH,
    INVESTMENT_OVERFLOW_REDIRECT_TO_SAVINGS,
)

ACCOUNTING_MODE_LEGACY = "legacy"
ACCOUNTING_MODE_LEDGER = "ledger"
ACCOUNTING_MODES = (ACCOUNTING_MODE_LEGACY, ACCOUNTING_MODE_LEDGER)

GOAL_CREDIT_FACE_VALUE = "face_value"
GOAL_CREDIT_GROWTH_WEIGHTED = "growth_weighted"
GOAL_CREDIT_MARKET_WEIGHTED = "market_weighted"
GOAL_CREDIT_MODES = (
    GOAL_CREDIT_FACE_VALUE,
    GOAL_CREDIT_GROWTH_WEIGHTED,
    GOAL_CREDIT_MARKET_WEIGHTED,
)

TARGET_BASIS_NOMINAL = "nominal"
TARGET_BASIS_INFLATED = "inflated"
TARGET_BASES = (TARGET_BASIS_NOMINAL, TARGET_BASIS_INFLATED)

# Reward versions (Phase D). The historical reward is never overwritten: every candidate is
# a separate, opt-in version selected by `reward_version`.
REWARD_VERSION_ARCHIVED = "archived_v1"
REWARD_VERSION_A = "candidate_a"   # goal-completion centric
REWARD_VERSION_B = "candidate_b"   # realised-wealth centric
REWARD_VERSIONS = (REWARD_VERSION_ARCHIVED, REWARD_VERSION_A, REWARD_VERSION_B)


@dataclass
class GoalPilotConfig:
    """Every assumption that can move a number in the RL environment or the LP.

    Defaults are chosen to be *archived-behaviour preserving* except for
    `accounting_mode`; see the class docstring note in the module header.
    """

    # ---- goal target basis (F-06) -----------------------------------------------------
    # "nominal"  : goal target = current_cost                      (archived RL behaviour)
    # "inflated" : goal target = current_cost * (1+infl)**(m/12)   (archived LP behaviour)
    target_basis: str = TARGET_BASIS_NOMINAL
    annual_inflation: float = 0.03

    # ---- cash-flow assumptions -------------------------------------------------------
    emergency_months: float = 0.0          # 0.0 = archived RL behaviour (LP used 6.0)
    emi_income_ratio_cap: float = 0.35     # matches the LP default

    # ---- vehicle returns -------------------------------------------------------------
    annual_savings_return: float = 0.0     # archived RL credits savings at face value
    investment_return_assumption: float = 0.05   # LP default; used by growth_weighted mode

    # ---- loan assumptions ------------------------------------------------------------
    loan_tenure_months: int = 60
    max_new_loan: float = 150_000.0

    # ---- behaviour switches ----------------------------------------------------------
    # "magnitude" (archived): the action is an absolute fraction of the available budget.
    #   budget_scale = min(1, budget / total_raw) never scales *up*, so a policy that
    #   emits values below the saturation point silently under-funds goals and the reward
    #   is flat above the saturation point -> no gradient (finding F-02).
    # "share": the action vector is normalised to shares, so the full available budget is
    #   always allocated. Removes the structural handicap against PPO.
    # "mix": identical to "share" except that investment demand above the user's investment
    #   capacity is left UNALLOCATED instead of being relabelled as savings. That single
    #   difference makes the requested savings/investment mix observable (finding R-12):
    #   under "share" an investment-only request silently becomes a savings-heavy policy
    #   because the overflow is pushed into the savings channel. Opt-in; every existing
    #   preset is unchanged.
    action_mode: str = ACTION_MODE_MAGNITUDE

    # The fate of investment demand above the user's capacity. "legacy" (default) reproduces
    # the historical, mode-dependent behaviour so that nothing published changes;
    # "retain_as_cash" and "redirect_to_savings" are explicit opt-in alternatives. See the
    # constant block at the top of this module for the full definitions.
    investment_overflow_policy: str = INVESTMENT_OVERFLOW_LEGACY

    # "legacy" : cash accumulates contributions, goal_balances ALSO contain them, and loan
    #   proceeds/EMI payments never touch an account. `cash + portfolio - loan` then
    #   double-counts contributions (F-04) and loans create goal assets with no liability
    #   settlement (F-05).
    # "ledger" : contributions move OUT of the discretionary flow INTO goal_balances,
    #   investment contributions move INTO the portfolio, loan proceeds credit cash and are
    #   then transferred to the goal, and every EMI payment debits cash. Contributions are
    #   counted exactly once. Reward- and goal-funding-neutral relative to "legacy".
    accounting_mode: str = ACCOUNTING_MODE_LEDGER

    # "face_value" (archived): a rupee contributed to a goal is worth one rupee of goal
    #   funding whatever the vehicle -> the savings/investment mix cannot affect goal
    #   funding at all (F-01).
    # "growth_weighted": savings contributions are compounded at annual_savings_return and
    #   investment contributions at investment_return_assumption up to the goal deadline,
    #   matching how the LP values contributions. The mix then matters. NOTE: the compounded
    #   amount is a *projection*, so goal funding exceeds the money actually contributed and
    #   the real market value of the portfolio (finding R-03). Kept for LP-parity work.
    # "market_weighted" (recommended): a new contribution is credited at face value, and the
    #   money already earmarked to each goal is then marked to market at the *realised* NIFTY
    #   monthly return, exactly like the portfolio. A projected return is never booked, so
    #   `sum(goal_balances) <= cash + portfolio` always holds, and the savings/investment mix
    #   still matters (the F-01 degeneracy stays broken) - but now for a real reason.
    goal_credit_mode: str = GOAL_CREDIT_FACE_VALUE

    # ---- reward design (Phase D) ------------------------------------------------------
    # "archived_v1" (default): the historical reward, byte-for-byte. Never modified.
    # "candidate_a": goal-completion centric - ratio-normalised progress, a GRADUATED
    #   shortfall signal over the last `shortfall_window_months` (instead of firing only in
    #   the exact deadline month), a debt-service penalty proportional to the month's
    #   interest cost relative to the budget, a DOWNSIDE-only risk charge on the money just
    #   invested (instead of a wealth-scaled charge on the whole portfolio), and a single
    #   terminal net-worth credit that cannot double-pay goal progress because goal balances
    #   are excluded from net worth.
    # "candidate_b": realised-wealth centric - one interpretable monthly wealth-delta term
    #   (which already nets interest and market outcomes) plus the same graduated shortfall
    #   signal and a single terminal achievement credit.
    reward_version: str = REWARD_VERSION_ARCHIVED

    # Candidate-reward parameters. These are DESIGN parameters, not fitted optima: they are
    # chosen so each term is of a comparable order to the per-goal progress term. See
    # outputs/reward_design/v1/REWARD_DESIGN_RATIONALE.md for the derivation and the
    # questions that remain open.
    shortfall_window_months: int = 12      # graduated shortfall horizon before a deadline
    loan_cost_weight: float = 5.0          # x (interest_cost / monthly budget)
    downside_risk_weight: float = 2.0      # x (downside return x money invested / budget)
    terminal_net_worth_weight: float = 2.0  # x (relative net-worth gain), final month only
    wealth_delta_weight: float = 2.0       # candidate B: x (net-worth delta / budget)
    terminal_achievement_weight: float = 3.0  # candidate B: x weighted achievement, final month

    # ---- allocation of cap-released budget (finding R-13) -----------------------------
    # False (default): the per-goal cap releases budget that is then discarded, exactly as the
    #   environment has always done. Measured cost: 26-29% of the monthly budget for the best
    #   simple policies and 36-51% for the trained RL policies
    #   (outputs/reward_design/v2/P1_STRATEGY_SPACE_DIAGNOSIS.md).
    # True: the released budget is reallocated to goals that still have remaining need, in
    #   proportion to that need, preserving the savings/investment split of the surviving
    #   allocation and respecting investment capacity.
    # Opt-in only. No existing preset enables it, so archived reproduction, every published
    # result and every existing checkpoint are unaffected.
    reallocate_capped_budget: bool = False

    # ---- space shaping / reproducibility ---------------------------------------------
    # Number of per-goal action slots. `None` infers `max(goals per user)` from whatever
    # subset is passed in — which means a checkpoint trained on the train split can be
    # incompatible with an environment built from the test split if their maximum goal
    # counts differ. Pin this to 5 (the value the archived checkpoint was trained with)
    # for any run that must load or compare against archived artefacts.
    n_goal_slots: int | None = None
    seed: int = 2026

    def __post_init__(self) -> None:
        if self.target_basis not in TARGET_BASES:
            raise ValueError(f"target_basis must be one of {TARGET_BASES}")
        if self.action_mode not in ACTION_MODES:
            raise ValueError(f"action_mode must be one of {ACTION_MODES}")
        if self.accounting_mode not in ACCOUNTING_MODES:
            raise ValueError(f"accounting_mode must be one of {ACCOUNTING_MODES}")
        if self.goal_credit_mode not in GOAL_CREDIT_MODES:
            raise ValueError(f"goal_credit_mode must be one of {GOAL_CREDIT_MODES}")
        if self.investment_overflow_policy not in INVESTMENT_OVERFLOW_POLICIES:
            raise ValueError(
                f"investment_overflow_policy must be one of {INVESTMENT_OVERFLOW_POLICIES}"
            )
        if self.reward_version not in REWARD_VERSIONS:
            raise ValueError(f"reward_version must be one of {REWARD_VERSIONS}")
        if self.shortfall_window_months < 0:
            raise ValueError("shortfall_window_months cannot be negative")
        if self.emergency_months < 0:
            raise ValueError("emergency_months cannot be negative")
        if not 0 < self.emi_income_ratio_cap <= 1:
            raise ValueError("emi_income_ratio_cap must be in (0, 1]")
        if self.loan_tenure_months <= 0:
            raise ValueError("loan_tenure_months must be positive")
        if self.max_new_loan < 0:
            raise ValueError("max_new_loan cannot be negative")
        if self.annual_inflation <= -1:
            raise ValueError("annual_inflation must be greater than -100%")
        if self.annual_savings_return <= -1:
            raise ValueError("annual_savings_return must be greater than -100%")
        if self.investment_return_assumption <= -1:
            raise ValueError("investment_return_assumption must be greater than -100%")
        if self.n_goal_slots is not None and self.n_goal_slots < 1:
            raise ValueError("n_goal_slots must be a positive integer or None")

    # ---- convenience -----------------------------------------------------------------

    @property
    def inflation_applies_to_goal_target(self) -> bool:
        return self.target_basis == TARGET_BASIS_INFLATED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def replace(self, **kwargs: Any) -> "GoalPilotConfig":
        return replace(self, **kwargs)

    # ---- presets used by the evaluation scripts --------------------------------------

    @classmethod
    def archived(cls) -> "GoalPilotConfig":
        """Exactly reproduces the archive that shipped on 2026-10-10."""
        return cls(
            target_basis=TARGET_BASIS_NOMINAL,
            action_mode=ACTION_MODE_MAGNITUDE,
            accounting_mode=ACCOUNTING_MODE_LEGACY,
            goal_credit_mode=GOAL_CREDIT_FACE_VALUE,
            emergency_months=0.0,
            annual_savings_return=0.0,
            n_goal_slots=5,          # the archived PPO checkpoint was trained with 5 slots
        )

    @classmethod
    def corrected_accounting(cls) -> "GoalPilotConfig":
        """Archived behaviour with a balanced ledger (F-04/F-05 fixed)."""
        return cls.archived().replace(accounting_mode=ACCOUNTING_MODE_LEDGER)

    @classmethod
    def lp_parity(cls) -> "GoalPilotConfig":
        """Settings that make the RL environment use the LP's target/assumption basis."""
        return cls.corrected_accounting().replace(
            target_basis=TARGET_BASIS_INFLATED,
            annual_inflation=0.03,
            emergency_months=6.0,
            annual_savings_return=0.0,
            investment_return_assumption=0.05,
        )

    @classmethod
    def recommended(cls) -> "GoalPilotConfig":
        """The configuration this audit recommends for the next training run.

        Not the default, because it changes goal-funding semantics and therefore
        invalidates the existing PPO checkpoint. Use it for a fresh training run.

        ``goal_credit_mode`` is ``market_weighted``: goal funding is credited from realised
        market revaluation only, never from a projected return (finding R-03).
        ``growth_weighted`` remains available and is used by the LP-parity experiments.
        """
        return cls.lp_parity().replace(
            action_mode=ACTION_MODE_SHARE,
            goal_credit_mode=GOAL_CREDIT_MARKET_WEIGHTED,
        )

    @classmethod
    def with_reallocation(cls) -> "GoalPilotConfig":
        """``recommended()`` plus the R-13 fix: budget released by the per-goal cap is
        reallocated to goals that still have remaining need.

        Deliberately a **separate** preset. Enabling the flag inside ``recommended()`` would
        silently change every published result and invalidate every existing checkpoint, so it
        stays opt-in and all existing presets are unchanged.
        """
        return cls.recommended().replace(reallocate_capped_budget=True)

    @classmethod
    def with_action_mix(cls) -> "GoalPilotConfig":
        """``recommended()`` plus the opt-in ``mix`` action mapping (finding R-12).

        In ``mix`` mode investment demand above the user's capacity stays unallocated instead
        of being relabelled as savings, so the requested savings/investment mix is observable.
        Opt-in and separate, so every existing preset, published result and checkpoint is
        untouched.
        """
        return cls.recommended().replace(action_mode=ACTION_MODE_MIX)

    @classmethod
    def with_investment_overflow(cls, policy: str) -> "GoalPilotConfig":
        """``recommended()`` plus an explicit policy for investment-cap overflow.

        ``policy`` is one of ``retain_as_cash`` or ``redirect_to_savings``; ``legacy`` is the
        default and is also accepted, but changes nothing. Opt-in and separate, so every
        existing preset, published result and checkpoint is untouched.
        """
        return cls.recommended().replace(investment_overflow_policy=policy)


DEFAULT_CONFIG = GoalPilotConfig()
