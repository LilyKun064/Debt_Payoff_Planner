# Credit Card Payoff Simulator (Streamlit)

A small Streamlit app to estimate debt payoff time and total interest under different payoff strategies.

## Features
- Save card nicknames + APR (first-time setup)
- Remember last-entered balances
- Optional one-time payments before simulating
- Strategy selector:
  - Avalanche (highest APR first)
  - Snowball (smallest balance first)
  - Proportional (split by balance)
- Compare $800/mo, $1000/mo, plus a custom monthly budget

## Local Run

### 1) Create & activate a virtual environment
**Windows PowerShell**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
**macOS/Linux**
```
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies
```
pip install -r requirements.txt
```

### 3) Start the app
```
streamlit run debt_app_streamlit.py
```