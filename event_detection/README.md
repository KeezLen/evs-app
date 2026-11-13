# Event detection

This is a standalone FastAPI boundary for the Energieverdienspel dashboard.
Zonnedael is available as validated daily, hourly, and 15-minute electricity
data. GridFlex remains unavailable; the rules, Isolation Forest, and RNN
forecast anomaly detectors are implemented.

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

For detector development, open `event_detection.html` after starting the API.
It is a separate analyst view for full-resolution data: the detector processes
all selected readings, while the chart uses spike-preserving downsampling and
the table shows merged event windows. It defaults to the 15-minute electricity
dataset and includes quality counts, event duration, detector selection, and
date filtering. The selected date range is the detection window; Isolation
Forest and RNN automatically use earlier available household readings as
training history when enough data exists.

For controlled detector comparisons, open `event_benchmark.html`. Select a
household for an immediate run, or choose all included households to run a
background batch with progress. The benchmark splits each series chronologically
70%/10%/20% for training, calibration, and test, and injects labeled changes
only into an in-memory copy of the test partition. These are synthetic
sensitivity tests, not appliance labels or naturally observed faults.

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
  `module` (`nilm` or `anomaly`), `method`, and optional `lookback_days` (1 or 7).
- `GET /event-summary` accepts the same dataset, household, range, module, and
  method parameters plus `lookback_days`, and returns quality counts, event
  totals, durations, and event windows for the analyst view.
- `GET /series-range?dataset=...&household=...` returns the recorded start and
  end dates for the selected household and dataset.
- `GET /benchmark/weather-audit?household=...` reports daily/hourly weather
  coverage, date alignment, temperature summary differences, and gas
  reconciliation.
- `POST /benchmark` runs one household synchronously or queues all included
  households and returns a job ID. Poll `GET /benchmark/jobs/{job_id}` for
  progress and results.
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
`incomplete`) and evaluates the selected detector against the transparent Klant
34 fixtures. Synthetic event rows are ground truth for evaluation only; they
are not appliance labels. Missing, partial, and absent dates are returned
separately as `data_quality`.

`/detect` with `module: "anomaly"` supports `method: "isolation_forest"` and
`method: "rnn"`. Isolation Forest fits separate household-specific models for valid
electricity and gas observations, using calendar and available weather context.
At least 30 valid observations are required per signal. The detector reports
generic `unusual_electricity` and `unusual_gas` events; it does not identify an
appliance or causal explanation. Partial and missing observations are excluded.
For interactive detection, Isolation Forest trains on earlier available history
and scores the selected detection window; it falls back to the provisional
chronological 70/30 split when earlier history is insufficient. Its 1%
contamination rate is an adjustable assumption.
Adjacent Isolation Forest intervals are merged into one event window. The
analyst summary reports the full event count and duration; its table limits the
visible rows for responsiveness.

The RNN method uses a per-household PyTorch LSTM to forecast the next hour:
four quarter-hour readings for 15-minute electricity, or one reading for
hourly electricity/gas. The analyst view offers 24-hour and 7-day input
lookbacks, defaulting to 24 hours. Models are cached in memory by their training
data and configuration. Separate high/low residual thresholds are calibrated
from the held-out final 20% of training windows using the 99th percentile.
Median +/- 3 MAD is a possible alternative: it is robust and compact, but less
responsive to skewed residual tails. RNN is currently limited to 15-minute and
hourly data; the prepared evaluation scenarios are daily and therefore do not
support RNN evaluation yet.

The benchmark currently compares Rules on daily data and Isolation Forest/RNN
on supported resolutions. Select event families and relative strengths in the
benchmark UI. It injects household-relative spikes (+50%, +100%,
+200%), low-use changes (-50%, -80%), and sustained high-use shifts (+30%,
+60% for 6 or 24 hours). Weather-aware gas injections are enabled only when the
weather audit passes; the audit currently finds complete daily/hourly
temperature coverage, aligned dates, and gas sums within 0.001 m3 on comparable
days. Mean daily/hourly temperature difference is about 0.11 C. KNMI De Bilt
remains a proxy because the households' actual location is unknown; each
resolution uses its own weather values.

Event matching is one-to-one and requires at least 50% ground-truth duration
overlap after a one-interval tolerance. Results include per-household and
macro precision/recall/F1, unmatched detections on injected test data, alerts on
the untouched test copy per household-week, detection delay, duration overlap,
and runtime. All-household runs use an in-memory job registry; job state does
not survive an API restart.

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
