"""
Credit card payoff simulator (multiple cards)

What it does:
- Store any number of cards (nickname, balance, APR)
- Apply a one-time payment to a specific card (updates its balance)
- Simulate payoff under:
    A) a *total* monthly budget (e.g., $800 or $1000) using a strategy (default: avalanche = highest APR first)
    B) a *manual* per-card payment plan each month (dict of {nickname: amount})

Outputs:
- Months to payoff
- Total interest paid
- Monthly payment schedule summary (and optional full per-month details)
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import copy
import math


@dataclass
class Card:
    name: str
    balance: float  # current balance
    apr: float      # APR in percent, e.g., 24.49 for 24.49%


def monthly_rate(apr_percent: float) -> float:
    return (apr_percent / 100.0) / 12.0


def apply_one_time_payment(cards: List[Card], card_name: str, amount: float) -> None:
    """Apply a one-time payment to a specific card (balance cannot go below 0)."""
    if amount < 0:
        raise ValueError("Payment amount must be >= 0")

    found = False
    for c in cards:
        if c.name == card_name:
            found = True
            c.balance = max(0.0, c.balance - amount)
            break
    if not found:
        raise KeyError(f"Card '{card_name}' not found. Available: {[c.name for c in cards]}")


def total_balance(cards: List[Card]) -> float:
    return sum(c.balance for c in cards)


def simulate_payoff_total_budget(
    cards: List[Card],
    monthly_budget: float,
    strategy: str = "avalanche",
    max_months: int = 2000,
    epsilon: float = 1e-6,
) -> Dict:
    """
    Simulate paying off all cards using a single total monthly budget.

    strategy:
      - "avalanche": pay highest APR first
      - "snowball": pay smallest balance first
      - "proportional": split budget by balance proportion each month
    """
    if monthly_budget <= 0:
        raise ValueError("monthly_budget must be > 0")

    cards = copy.deepcopy(cards)

    months = 0
    total_interest_paid = 0.0
    history = []  # optional: per-month snapshots

    while total_balance(cards) > epsilon:
        months += 1
        if months > max_months:
            return {
                "paid_off": False,
                "months": months,
                "total_interest": total_interest_paid,
                "reason": "Hit max_months (budget may be too low).",
                "history": history,
            }

        # 1) Accrue interest
        month_interest = 0.0
        for c in cards:
            if c.balance > epsilon:
                intr = c.balance * monthly_rate(c.apr)
                c.balance += intr
                month_interest += intr
        total_interest_paid += month_interest

        # 2) Allocate payments
        remaining_budget = monthly_budget

        # Build payoff order
        active = [c for c in cards if c.balance > epsilon]
        if strategy == "avalanche":
            active.sort(key=lambda x: (-x.apr, x.balance))
        elif strategy == "snowball":
            active.sort(key=lambda x: (x.balance, -x.apr))
        elif strategy == "proportional":
            # handled below
            pass
        else:
            raise ValueError("strategy must be one of: avalanche, snowball, proportional")

        if strategy == "proportional":
            total_bal = sum(c.balance for c in active)
            if total_bal <= epsilon:
                break
            for c in active:
                share = remaining_budget * (c.balance / total_bal)
                pay = min(c.balance, share)
                c.balance -= pay
            remaining_budget = 0.0
        else:
            for c in active:
                if remaining_budget <= epsilon:
                    break
                pay = min(c.balance, remaining_budget)
                c.balance -= pay
                remaining_budget -= pay

            # If we paid off cards and still have budget, loop again over any remaining balances
            # (rare unless the budget is very large)
            if remaining_budget > epsilon:
                active2 = [c for c in cards if c.balance > epsilon]
                active2.sort(key=lambda x: (-x.apr, x.balance)) if strategy == "avalanche" else active2.sort(key=lambda x: (x.balance, -x.apr))
                for c in active2:
                    if remaining_budget <= epsilon:
                        break
                    pay = min(c.balance, remaining_budget)
                    c.balance -= pay
                    remaining_budget -= pay

        # 3) Record history snapshot
        history.append({
            "month": months,
            "interest": month_interest,
            "total_interest_to_date": total_interest_paid,
            "balances": {c.name: max(0.0, c.balance) for c in cards},
            "total_balance": total_balance(cards),
        })

    return {
        "paid_off": True,
        "months": months,
        "total_interest": total_interest_paid,
        "monthly_budget": monthly_budget,
        "strategy": strategy,
        "history": history,
    }


def simulate_payoff_manual_payments(
    cards: List[Card],
    monthly_payments: Dict[str, float],
    max_months: int = 2000,
    epsilon: float = 1e-6,
) -> Dict:
    """
    Simulate payoff using a fixed manual payment per card each month.
    Example monthly_payments = {"Chase": 600, "Discover": 200}

    Note: if you overpay a card (payment > balance), the extra does NOT automatically roll to others here.
          (You can add that behavior if you want.)
    """
    cards = copy.deepcopy(cards)
    for k, v in monthly_payments.items():
        if v < 0:
            raise ValueError(f"Payment for {k} must be >= 0")

    name_to_card = {c.name: c for c in cards}

    months = 0
    total_interest_paid = 0.0
    history = []

    while total_balance(cards) > epsilon:
        months += 1
        if months > max_months:
            return {
                "paid_off": False,
                "months": months,
                "total_interest": total_interest_paid,
                "reason": "Hit max_months (payments may be too low).",
                "history": history,
            }

        # accrue interest
        month_interest = 0.0
        for c in cards:
            if c.balance > epsilon:
                intr = c.balance * monthly_rate(c.apr)
                c.balance += intr
                month_interest += intr
        total_interest_paid += month_interest

        # apply payments
        for name, pay_amt in monthly_payments.items():
            if name not in name_to_card:
                raise KeyError(f"Card '{name}' not found. Available: {list(name_to_card.keys())}")
            c = name_to_card[name]
            if c.balance > epsilon and pay_amt > 0:
                pay = min(c.balance, pay_amt)
                c.balance -= pay

        history.append({
            "month": months,
            "interest": month_interest,
            "total_interest_to_date": total_interest_paid,
            "balances": {c.name: max(0.0, c.balance) for c in cards},
            "total_balance": total_balance(cards),
        })

    return {
        "paid_off": True,
        "months": months,
        "total_interest": total_interest_paid,
        "monthly_payments": monthly_payments,
        "history": history,
    }


def compare_budgets(cards: List[Card], budgets: List[float], strategy: str = "avalanche") -> None:
    """Print a simple comparison table for different monthly budgets."""
    print(f"\nComparison (strategy = {strategy})")
    print("-" * 70)
    print(f"{'Budget/mo':>10} | {'Months':>7} | {'Total interest':>15} | {'Total paid':>12}")
    print("-" * 70)

    for b in budgets:
        res = simulate_payoff_total_budget(cards, monthly_budget=b, strategy=strategy)
        if not res["paid_off"]:
            print(f"{b:>10.2f} | {'N/A':>7} | {'N/A':>15} | {'N/A':>12}  ({res['reason']})")
            continue
        months = res["months"]
        total_interest = res["total_interest"]
        principal = sum(c.balance for c in cards)
        total_paid = principal + total_interest
        print(f"{b:>10.2f} | {months:>7} | {total_interest:>15.2f} | {total_paid:>12.2f}")
    print("-" * 70)

def pick_card_interactively(cards: List[Card]) -> str:
    """Let user select a card by number or name; returns the card name."""
    print("\nYour cards:")
    for i, c in enumerate(cards, start=1):
        print(f"  {i}) {c.name}  | balance={c.balance:.2f} | APR={c.apr:.2f}%")

    while True:
        choice = input("\nSelect a card (enter number or exact nickname, or 'q' to cancel): ").strip()
        if choice.lower() == "q":
            raise KeyboardInterrupt("User cancelled card selection.")
        # number?
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(cards):
                return cards[idx - 1].name
            print("Invalid number. Try again.")
            continue
        # name?
        names = [c.name for c in cards]
        if choice in names:
            return choice
        print("Not a valid nickname. Try again.")


def ask_payments_interactively(cards: List[Card]) -> Dict[str, float]:
    """
    Ask user for one or more payments.
    Returns dict {card_name: total_payment_for_that_card}
    """
    payments: Dict[str, float] = {}

    print("\nEnter payments you made THIS MONTH (you can enter multiple).")
    print("Tips:")
    print(" - You can pay the same card multiple times; it will add up.")
    print(" - Type 'done' when finished.\n")

    while True:
        cmd = input("Type 'add' to enter a payment, or 'done' to finish: ").strip().lower()
        if cmd == "done":
            break
        if cmd != "add":
            print("Please type 'add' or 'done'.")
            continue

        card_name = pick_card_interactively(cards)

        while True:
            amt_str = input(f"Payment amount to {card_name}: ").strip()
            try:
                amt = float(amt_str)
                if amt < 0:
                    print("Amount must be >= 0. Try again.")
                    continue
                break
            except ValueError:
                print("Please enter a number like 400 or 125.50")

        payments[card_name] = payments.get(card_name, 0.0) + amt
        print(f"Recorded: {card_name} += {amt:.2f} (total for this card: {payments[card_name]:.2f})\n")

    return payments


def apply_payments(cards: List[Card], payments: Dict[str, float]) -> None:
    """Apply a batch of payments to balances."""
    for card_name, amt in payments.items():
        apply_one_time_payment(cards, card_name=card_name, amount=amt)

def prompt_update_balances(cards: List[Card]) -> None:
    """
    Ask user to enter the current balance for each card.
    Press Enter to keep the existing balance shown.
    """
    print("\nEnter CURRENT balances for each card (press Enter to keep current value).")
    for c in cards:
        while True:
            s = input(f"{c.name} (APR {c.apr:.2f}%) current={c.balance:.2f} -> new balance: ").strip()
            if s == "":
                break  # keep as-is
            try:
                new_bal = float(s)
                if new_bal < 0:
                    print("Balance cannot be negative. Try again.")
                    continue
                c.balance = new_bal
                break
            except ValueError:
                print("Please enter a number like 1234.56 (or press Enter).")


if __name__ == "__main__":
    # 1) Define your cards (edit these)
    cards = [
        Card(name="Chase_Kun", balance=14752.93, apr=27.49),
        Card(name="Discover_Kun", balance=3381.41, apr=24.49),
        Card(name="BOA_Kai", balance=2458, apr=27.49),
        Card(name="Chase_Kai", balance=3323.79, apr=27.49),
        Card(name="Discover_Kai", balance=2452.71, apr=24.49),
    ]

    # Ask user to update balances (APR + names stay the same)
    prompt_update_balances(cards)
    
    # 2) Apply what you paid this month to a specific card (optional)
    try:
        payments = ask_payments_interactively(cards)
        if payments:
            apply_payments(cards, payments)
            print("\nBalances after applying this month's payments:")
            for c in cards:
                print(f"  {c.name}: {c.balance:.2f}")
        else:
            print("\nNo payments entered. Using current balances as-is.")
    except KeyboardInterrupt:
        print("\nPayment entry cancelled. Using current balances as-is.")


    # 3) Compare payoff if you pay $800 vs $1000 total per month (default strategy: avalanche)
    compare_budgets(cards, budgets=[800.0, 1000.0], strategy="avalanche")

    # 4) If you want the full details for one scenario:
    result_800 = simulate_payoff_total_budget(cards, monthly_budget=800.0, strategy="avalanche")
    print("\nDetails for $800/mo:")
    print(f"Months to payoff: {result_800['months']}")
    print(f"Total interest:   {result_800['total_interest']:.2f}")

    result_1000 = simulate_payoff_total_budget(cards, monthly_budget=1000.0, strategy="avalanche")
    print("\nDetails for $1000/mo:")
    print(f"Months to payoff: {result_1000['months']}")
    print(f"Total interest:   {result_1000['total_interest']:.2f}")

    # 5) Custom monthly payment amounts (loop)
    while True:
        s = input("\nEnter a custom monthly payment amount (or 'q' to quit custom): ").strip().lower()
        if s in ("q", "quit", "exit", ""):
            break
        try:
            custom_amt = float(s)
            if custom_amt <= 0:
                print("Amount must be > 0.")
                continue
            result_custom = simulate_payoff_total_budget(cards, monthly_budget=custom_amt, strategy="avalanche")
            print(f"\nDetails for ${custom_amt:.2f}/mo:")
            print(f"Months to payoff: {result_custom['months']}")
            print(f"Total interest:   {result_custom['total_interest']:.2f}")
        except ValueError:
            print("Please enter a number like 900 or 1250.50, or 'q' to quit.")

   
