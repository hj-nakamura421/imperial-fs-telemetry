# Formula Student EV Drivetrain Telemetry

[![CI](https://github.com/hj-nakamura421/imperial-fs-telemetry/actions/workflows/ci.yml/badge.svg)](https://github.com/hj-nakamura421/imperial-fs-telemetry/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)

A focused Python and Streamlit dashboard for turning electric Formula Student
test logs into lap-level performance, thermal and accumulator evidence.

Upload a CSV from a dyno or track session and the app validates its schema,
plots the core drivetrain channels, integrates energy without assuming a fixed
sample rate, and flags threshold violations with the affected laps.

> **Portfolio status:** the included run is synthetic and the default limits
> are illustrative. This repository demonstrates the analysis workflow; it is
> not an official Imperial Racing tool or a substitute for vehicle safety
> systems.

## Engineering questions it answers

| Question | Evidence in the dashboard |
|---|---|
| Where did performance change? | RPM, torque and mechanical power traces plus per-lap summaries |
| Did the thermal system stay inside limits? | Motor and inverter trends with editable thresholds |
| Did the accumulator sag under load? | Pack voltage and current traces with lap-level flags |
| How much mechanical energy was delivered? | Trapezoidal integration of power over timestamped samples |
| Can an uploaded log be trusted? | Required-column, numeric, finite-value and time-order validation |

## Quick start

With [`uv`](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/hj-nakamura421/imperial-fs-telemetry.git
cd imperial-fs-telemetry
uv sync --dev
uv run python data_generator.py
uv run streamlit run app.py
```

Or with `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python data_generator.py
streamlit run app.py
```

Then open <http://localhost:8501>. The synthetic sample is selected by default;
you can replace it with a compatible CSV from the sidebar.

## Data contract

| Column | Unit | Meaning |
|---|---:|---|
| `time_s` | s | Elapsed session time, ordered earliest to latest |
| `lap` | integer | Positive, one-indexed lap number |
| `motor_rpm` | rpm | Motor shaft speed |
| `motor_torque_nm` | N·m | Motor torque |
| `power_kw` | kW | Instantaneous mechanical power |
| `motor_temp_c` | °C | Motor stator temperature |
| `inverter_temp_c` | °C | Inverter heatsink temperature |
| `battery_voltage_v` | V | High-voltage pack terminal voltage |
| `battery_current_a` | A | High-voltage pack current draw |

## Design

```text
CSV upload / synthetic run
          │
          ▼
Schema and signal validation ── telemetry.py
          │
          ├── Threshold anomaly detection
          ├── Headline metrics
          └── Sample-rate-independent lap summaries
          │
          ▼
Interactive review ──────────── app.py / Streamlit / Plotly
```

The analysis lives in `telemetry.py`, separate from the interface, so its
behaviour can be tested without starting Streamlit. CI exercises the supported
Python versions on every pull request.

## Verify

```bash
uv run pytest
```

The tests cover data-contract failures, headline metrics, anomaly attribution
and energy integration.

## Default review thresholds

- Motor temperature: **100 °C**
- Inverter temperature: **80 °C**
- Pack voltage sag: **540 V**

All three can be changed from the sidebar at runtime.

## Stack

Python · Streamlit · pandas · NumPy · Plotly · pytest · GitHub Actions

## Author

HJ Nakamura — Mechanical Engineering, Imperial College London
