# Imperial FS Drivetrain Telemetry Analyzer

A small web dashboard for making sense of drivetrain test data from the
Imperial College London Formula Student electric car.

Drop in a CSV from a dyno or track test, get motor / thermal / electrical
plots and a per-lap summary, with automatic flags for overtemp and pack
voltage sag.

## Why

We were spending evenings squinting at Excel. This is meant to be the thing
you open immediately after a test run to see whether anything obvious went
wrong, before doing the deeper analysis.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python data_generator.py     # writes data/sample_run.csv
streamlit run app.py
```

Then open <http://localhost:8501>. Either upload your own CSV (sidebar) or
click **Use sample run**.

## CSV format

The dashboard expects the following columns (10 Hz sampling assumed for the
energy integral):

| column                | unit  | notes                                  |
|-----------------------|-------|----------------------------------------|
| `time_s`              | s     | elapsed time from session start        |
| `lap`                 | int   | 1-indexed lap number                   |
| `motor_rpm`           | rpm   | motor shaft speed                      |
| `motor_torque_nm`     | Nm    | motor torque                           |
| `power_kw`            | kW    | instantaneous mechanical power         |
| `motor_temp_c`        | °C    | motor stator temperature               |
| `inverter_temp_c`     | °C    | inverter heatsink temperature          |
| `battery_voltage_v`   | V     | HV pack terminal voltage               |
| `battery_current_a`   | A     | HV pack current draw                   |

## Default thresholds

Editable in the sidebar at runtime:

- Motor temperature: **100 °C**
- Inverter temperature: **80 °C**
- Pack voltage sag: **540 V** (against 600 V nominal)

## Stack

- Python 3.13
- Streamlit · pandas · numpy · plotly

Built as a sketch of what a focused single-purpose tool can look like for
an FS team — fast to extend, no infrastructure, runs locally.
