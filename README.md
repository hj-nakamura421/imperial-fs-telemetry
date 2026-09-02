# Formula Student EV Drivetrain Telemetry Debrief

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://imperial-fs-telemetry.streamlit.app/)
[![CI](https://github.com/hj-nakamura421/imperial-fs-telemetry/actions/workflows/ci.yml/badge.svg)](https://github.com/hj-nakamura421/imperial-fs-telemetry/actions/workflows/ci.yml)

**Live application:** [imperial-fs-telemetry.streamlit.app](https://imperial-fs-telemetry.streamlit.app/)

A small, review-led telemetry tool for Formula Student EV test sessions. It turns timestamped drivetrain signals into a concise debrief: thermal and voltage-sag events, lap-level energy use, and a clearly stated next check for each issue.

> **Data boundary:** the committed CSV is deterministic, labelled **synthetic** data designed to demonstrate the analysis path. It is not an official Imperial Formula Student log or evidence that the tool has been deployed by a team.

## The engineering problem

After a test run, an engineer needs decisions quickly—not a dashboard full of unrelated traces. This tool addresses the practical first questions in an EV drivetrain debrief:

| Review question | Implementation |
| --- | --- |
| Did a motor or inverter thermal limit need attention? | Consecutive threshold breaches are grouped into timestamped review windows. |
| Did the accumulator sag under load? | Pack-voltage events are flagged alongside the minimum voltage and maximum sag. |
| Did energy demand change from lap to lap? | Mechanical and electrical power are integrated over each lap using the recorded timestamps. |
| Can this uploaded log be trusted enough to interpret? | The input schema, numeric fields, time ordering, and lap numbering are validated before analysis. |
| What should happen next? | Each review window includes a deliberately specific engineering prompt, such as checking coolant flow, torque demand or BMS limits. |

The bundled scenario deliberately creates one motor-temperature event, one inverter-temperature event and one voltage-sag event, so the end-to-end review path can be tested and demonstrated.

## What makes this more than a chart

- **Timestamp-aware energy accounting.** Mechanical power and `voltage × current` electrical power are integrated with the trapezoidal rule, rather than assuming a fixed sampling period.
- **Review windows, not thousands of red points.** Adjacent samples over a limit are collapsed into one event with duration, affected laps, worst value, severity and an investigation prompt.
- **Transparent assumptions.** Nominal pack voltage and review thresholds are explicit, adjustable inputs; estimated drivetrain efficiency is marked as a first-pass diagnostic, not a calibrated loss model.
- **Reliable input handling.** Invalid CSVs fail with a useful validation message before plots or metrics are produced.
- **Tested analysis layer.** The event grouping, energy calculations, validation and demonstration scenario are covered by automated tests and GitHub Actions.

## Run it locally

```bash
uv sync --dev
uv run python data_generator.py
uv run streamlit run app.py
```

To run the tests:

```bash
uv run pytest
```

## CSV contract

Upload a CSV with these columns:

```text
time_s, lap, motor_rpm, motor_torque_nm, power_kw,
motor_temp_c, inverter_temp_c, battery_voltage_v, battery_current_a
```

`time_s` must be ordered from earliest to latest. All signals must be numeric, and `lap` must contain positive integers.

## Engineering workflow

```text
test log → schema checks → signal/event detection → energy & lap summary → review log → targeted follow-up
```

This repository is intentionally scoped as a portfolio-quality analysis prototype. A truthful team case study would next use a permissioned, anonymised real test log and document the resulting investigation or engineering decision.

## Stack

Python · pandas · NumPy · Streamlit · Plotly · pytest · GitHub Actions

Built by [HJ Nakamura](https://github.com/hj-nakamura421), Mechanical Engineering student at Imperial College London.
