# Event detection

This is a standalone FastAPI boundary for the Energieverdienspel dashboard.
Zonnedael is available as validated daily, hourly, and 15-minute electricity
data. GridFlex remains unavailable; the initial rules and Isolation Forest
anomaly detectors are implemented.

## Run

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn event_detection.api.app:app --reload
```

Run these commands from the repository root (`evs-app`). If PowerShell blocks
the activation script, use the virtual environment directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn event_detection.api.app:app --reload
```

The dashboard uses `http://127.0.0.1:8000` by default. Override it before
opening the HTML with `window.EVS_EVENT_API_BASE_URL`.

To use the event-detection tab, start the API and open `index.html`. Select
`Zonnedael`, enter an included household such as `Klant 34`, optionally choose
a date range, and click **Run detection**. The tab loads the selected series
before running the detector and plots valid electricity readings; gaps remain
visible as breaks in the chart.

## API

- `GET /datasets` returns the catalog and availability notes.
- `GET /series?dataset=...&household=...` returns normalized points for
  included Zonnedael households. The dataset IDs are `zonnedael` (daily),
  `zonnedael_hourly` (hourly electricity, gas, and temperature), and
  `zonnedael_15min_electricity` (quarter-hour electricity only).
- `POST /detect` accepts `dataset`, `household`, `range_start`, `range_end`,
  `module` (`nilm` or `anomaly`) and `method`.
- `POST /evaluate` uses the same request plus `tolerance_minutes` and a
  `scenario`.

  Scenario evaluation currently uses the prepared `Klant 34` fixtures
  regardless of which household is selected for normal detection. The frontend
  labels this explicitly and sends the fixture household automatically, so
  changing household does not cause a failed evaluation request.

`/detect` uses the initial `rules` method for valid daily points. It compares
electricity with the household median and gas with a robust heating-degree-day
baseline. Gas detection requires at least 14 valid observations so short date
ranges are not treated as a reliable household profile. Partial and missing
points are ignored, not treated as zero use.
`/evaluate` accepts `scenario` (`normal`, `high_use`, `missing`, or
`incomplete`) and evaluates the rules against the transparent Klant 34
fixtures. Synthetic event rows are ground truth for evaluation only; they are
not appliance labels. Missing, partial, and absent dates are returned
separately as `data_quality`.

`/detect` with `module: "anomaly"` currently supports `method:
"isolation_forest"`. It fits separate household-specific models for valid
electricity and gas observations, using calendar and available weather context.
At least 30 valid observations are required per signal. The detector reports
generic `unusual_electricity` and `unusual_gas` events; it does not identify an
appliance or causal explanation. Partial and missing observations are excluded.

## Adding data

Implement `DatasetLoader` in `event_detection/data/loaders.py` for new sources.
The Zonnedael loaders return normalized `SeriesPoint` values while preserving
quality flags and missing values. The daily loader also includes weather and
household metadata. All loaders expose only homes marked `included=True` in
`household_summary.csv`.

## Adding detectors

Implement `Detector` in `event_detection/nilm/base.py`, give it a unique
`name`, and register it in `detector_registry`. The API and dashboard select
methods by name, so HMM or deep-learning methods can be added without changing
the JSON contract. Anomaly detectors stay in `event_detection/anomaly/`.

The initial rules are deliberately conservative and generic: they report
`high_electricity` and `high_gas`, not appliance names. The thresholds are
documented in `event_detection/nilm/rules.py` and are intended as a baseline
for later prediction methods. Event end times follow each point's interval
length, so granular detections are bounded to one hour or 15 minutes.

Evaluation defaults to a one-day event-start tolerance because Zonnedael is a
daily dataset. A smaller tolerance can still be supplied explicitly.

## Ground truth

Evaluation is separate from detection. The scenario files provide explicit
synthetic events and gaps for development.
They should not be presented as verified appliance-level ground truth. The
evaluation response identifies the selected scenario and reports data-quality
findings independently from consumption metrics.
