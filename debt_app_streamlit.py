import json
import os
import copy
from dataclasses import dataclass
from typing import Dict, List, Optional

import streamlit as st

META_FILE = "cards_meta.json"
BAL_FILE = "balances.json"


# ---------------- Core logic ----------------

@dataclass
class Card:
    name: str
    balance: float
    apr: float  # percent


def monthly_rate(apr_percent: float) -> float:
    return (apr_percent / 100.0) / 12.0


def total_balance(cards: List[Card]) -> float:
    return sum(c.balance for c in cards)


def apply_one_time_payment(cards: List[Card], card_name: str, amount: float) -> None:
    if amount < 0:
        raise ValueError("Payment amount must be >= 0")
    for c in cards:
        if c.name == card_name:
            c.balance = max(0.0, c.balance - amount)
            return
    raise KeyError(f"Card '{card_name}' not found.")


def simulate_payoff_total_budget(
    cards: List[Card],
    monthly_budget: float,
    strategy: str = "avalanche",
    max_months: int = 2000,
    epsilon: float = 1e-6,
) -> Dict:
    if monthly_budget <= 0:
        raise ValueError("monthly_budget must be > 0")

    cards = copy.deepcopy(cards)
    months = 0
    total_interest_paid = 0.0

    while total_balance(cards) > epsilon:
        months += 1
        if months > max_months:
            return {
                "paid_off": False,
                "months": months,
                "total_interest": total_interest_paid,
                "reason": "Hit max_months (budget may be too low).",
            }

        # 1) interest accrues
        for c in cards:
            if c.balance > epsilon:
                intr = c.balance * monthly_rate(c.apr)
                c.balance += intr
                total_interest_paid += intr

        # 2) allocate payments
        remaining = monthly_budget
        active = [c for c in cards if c.balance > epsilon]

        if strategy == "avalanche":
            active.sort(key=lambda x: (-x.apr, x.balance))
            for c in active:
                if remaining <= epsilon:
                    break
                pay = min(c.balance, remaining)
                c.balance -= pay
                remaining -= pay

        elif strategy == "snowball":
            active.sort(key=lambda x: (x.balance, -x.apr))
            for c in active:
                if remaining <= epsilon:
                    break
                pay = min(c.balance, remaining)
                c.balance -= pay
                remaining -= pay

        elif strategy == "proportional":
            total_bal = sum(c.balance for c in active)
            if total_bal <= epsilon:
                break
            for c in active:
                share = remaining * (c.balance / total_bal)
                pay = min(c.balance, share)
                c.balance -= pay

        else:
            raise ValueError("Unknown strategy")

    return {
        "paid_off": True,
        "months": months,
        "total_interest": total_interest_paid,
    }


# ---------------- Persistence ----------------

def load_meta() -> List[Dict]:
    if not os.path.exists(META_FILE):
        return []
    with open(META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_meta(meta: List[Dict]) -> None:
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def load_balances() -> Dict[str, float]:
    if not os.path.exists(BAL_FILE):
        return {}
    with open(BAL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {k: float(v) for k, v in data.items()}


def save_balances(balances: Dict[str, float]) -> None:
    with open(BAL_FILE, "w", encoding="utf-8") as f:
        json.dump(balances, f, indent=2)


def persist_current_balances(meta: List[Dict]) -> None:
    """Save current balance widgets to BAL_FILE."""
    out: Dict[str, float] = {}
    for m in meta:
        name = m["name"]
        key = f"bal::{name}"
        out[name] = float(st.session_state.get(key, 0.0))
    save_balances(out)


# ---------------- UI helpers ----------------

STRATEGIES = {
    "avalanche": {
        "label": "Avalanche (highest APR first)",
        "meaning": "Puts extra money toward the highest APR card first. Usually minimizes total interest.",
    },
    "snowball": {
        "label": "Snowball (smallest balance first)",
        "meaning": "Pays off the smallest balance first. Often feels motivating; may cost more interest.",
    },
    "proportional": {
        "label": "Proportional (split by balance)",
        "meaning": "Splits your monthly budget across cards in proportion to their balances.",
    },
}


def build_cards_from_inputs(meta: List[Dict], saved_balances: Optional[Dict[str, float]] = None) -> List[Card]:
    """
    Build Card objects from Streamlit widget state.

    Priority for balance value:
      1) st.session_state["bal::<name>"] if present
      2) saved_balances[<name>] if provided
      3) 0.0
    """
    saved_balances = saved_balances or {}
    cards: List[Card] = []

    for m in meta:
        name = str(m.get("name", "")).strip()
        if not name:
            continue

        apr = float(m.get("apr", 0.0))
        key = f"bal::{name}"

        if key not in st.session_state:
            st.session_state[key] = float(saved_balances.get(name, 0.0))

        bal = float(st.session_state.get(key, saved_balances.get(name, 0.0)))
        if bal < 0:
            bal = 0.0

        cards.append(Card(name=name, balance=bal, apr=apr))

    return cards


def principal_sum(cards: List[Card]) -> float:
    return sum(c.balance for c in cards)


def render_result(title: str, cards: List[Card], res: Dict):
    principal = principal_sum(cards)
    if not res["paid_off"]:
        st.error(f"{title}: Not paid off within limit. ({res.get('reason','')})")
        return

    total_interest = res["total_interest"]
    total_paid = principal + total_interest

    c1, c2, c3 = st.columns(3)
    c1.metric(f"{title} • Months", f"{res['months']}")
    c2.metric(f"{title} • Total interest", f"${total_interest:,.2f}")
    c3.metric(f"{title} • Total paid", f"${total_paid:,.2f}")


# ---------------- App ----------------

st.set_page_config(page_title="Debt Payoff App", layout="wide")
st.title("Credit Card Payoff Simulator")

meta = load_meta()
saved_balances = load_balances()

with st.sidebar:
    st.header("Strategy")
    for _, info in STRATEGIES.items():
        st.markdown(f"**{info['label']}**  \n{info['meaning']}\n")

    st.divider()

    strategy = st.radio(
        "Click to choose a payoff strategy:",
        options=list(STRATEGIES.keys()),
        format_func=lambda k: STRATEGIES[k]["label"],
        index=0,
        key="strategy_select",
    )

    st.divider()
    st.header("Card setup (name + APR)")

    if not meta:
        st.info("First run: enter your cards once. This will be saved locally.")
        if "setup_rows" not in st.session_state:
            st.session_state["setup_rows"] = [{"name": "", "apr": 0.0}]

        colA, colB = st.columns(2)
        if colA.button("Add another card"):
            st.session_state["setup_rows"].append({"name": "", "apr": 0.0})
        if colB.button("Remove last") and len(st.session_state["setup_rows"]) > 1:
            st.session_state["setup_rows"].pop()

        new_rows = []
        for i, row in enumerate(st.session_state["setup_rows"]):
            st.markdown(f"**Card {i+1}**")
            name = st.text_input("Nickname", value=row["name"], key=f"setup_name_{i}")
            apr = st.number_input("APR (%)", value=float(row["apr"]), min_value=0.0, step=0.01, key=f"setup_apr_{i}")
            new_rows.append({"name": name.strip(), "apr": float(apr)})

        if st.button("Save cards"):
            cleaned = []
            seen = set()
            for r in new_rows:
                if not r["name"]:
                    continue
                if r["name"] in seen:
                    st.error(f"Duplicate nickname: {r['name']}")
                    st.stop()
                seen.add(r["name"])
                cleaned.append({"name": r["name"], "apr": float(r["apr"])})

            if not cleaned:
                st.error("Please enter at least one card.")
                st.stop()

            save_meta(cleaned)
            st.success(f"Saved {len(cleaned)} cards to {META_FILE}. Refreshing…")
            st.rerun()

    else:
        st.success(f"Loaded {len(meta)} saved cards from {META_FILE}.")
        st.caption("You won’t need to re-enter APRs unless you reset.")
        if st.button("Reset saved cards (delete memory)"):
            try:
                os.remove(META_FILE)
            except FileNotFoundError:
                pass
            st.warning("Deleted saved cards. Refreshing…")
            st.rerun()

        if st.button("Reset saved balances"):
            try:
                os.remove(BAL_FILE)
            except FileNotFoundError:
                pass
            st.warning("Deleted balances.json. Refreshing…")
            st.rerun()


if not meta:
    st.stop()

st.subheader("1) Enter current balances (defaults to last run)")
st.write("Balances auto-fill from your last run. Click **Run simulation** to compute and auto-save balances.")

# Balance inputs (default to saved_balances)
for m in meta:
    name = m["name"]
    apr = float(m["apr"])
    key = f"bal::{name}"

    # default only once per session
    if key not in st.session_state:
        st.session_state[key] = float(saved_balances.get(name, 0.0))

    st.number_input(
        f"{name} (APR {apr:.2f}%) balance",
        min_value=0.0,
        step=10.0,
        key=key,
    )

st.subheader("2) Optional: payments already made this month")
st.write("These payments reduce balances BEFORE simulations (they do not change your saved APRs/names).")

pay_cols = st.columns(2)
with pay_cols[0]:
    pay_card = st.selectbox("Which card?", options=[m["name"] for m in meta], key="pay_card")
with pay_cols[1]:
    pay_amt = st.number_input("Payment amount", min_value=0.0, step=10.0, key="pay_amt")

if st.button("Add this payment"):
    st.session_state.setdefault("payment_list", [])
    st.session_state["payment_list"].append({"card": pay_card, "amt": float(pay_amt)})
    st.success("Added.")

payment_list = st.session_state.get("payment_list", [])
if payment_list:
    st.write("Payments entered:")
    for idx, p in enumerate(payment_list):
        c1, c2 = st.columns([6, 1])
        c1.write(f"- {p['card']}: ${p['amt']:.2f}")
        if c2.button("Remove", key=f"rm_{idx}"):
            st.session_state["payment_list"].pop(idx)
            st.rerun()
    if st.button("Clear all payments"):
        st.session_state["payment_list"] = []
        st.rerun()

st.subheader("3) Run payoff estimates")
left, right = st.columns([2, 1])

with left:
    custom_budget = st.number_input("Custom monthly budget (optional)", min_value=0.0, step=50.0, value=0.0, key="custom_budget")

with right:
    run = st.button("Run simulation", type="primary")

if run:
    # AUTO-SAVE balances immediately when user runs
    persist_current_balances(meta)
    st.toast("Saved balances to balances.json", icon="✅")

    cards = build_cards_from_inputs(meta, saved_balances=saved_balances)

    # Apply one-time payments for simulation
    for p in st.session_state.get("payment_list", []):
        apply_one_time_payment(cards, p["card"], p["amt"])

    st.markdown(f"### Results (Strategy: **{STRATEGIES[strategy]['label']}**)")

    res_800 = simulate_payoff_total_budget(cards, monthly_budget=800.0, strategy=strategy)
    render_result("$800/mo", cards, res_800)

    res_1000 = simulate_payoff_total_budget(cards, monthly_budget=1000.0, strategy=strategy)
    render_result("$1000/mo", cards, res_1000)

    if custom_budget and custom_budget > 0:
        res_custom = simulate_payoff_total_budget(cards, monthly_budget=float(custom_budget), strategy=strategy)
        render_result(f"${custom_budget:,.2f}/mo", cards, res_custom)
else:
    st.info("Choose a strategy in the sidebar, enter balances, then click **Run simulation**.")
