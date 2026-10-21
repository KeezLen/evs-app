# Event detection

This is a standalone FastAPI boundary for the Energieverdienspel dashboard.
It is intentionally data-ready but data-empty: the data team owns the public
GridFlex Heeten and Zonnedael adapters and their validation/resampling.

## Run

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn event_detection.api.app:app --reload
```

The dashboard uses `http://127.0.0.1:8000` by default. Override it before
opening the HTML with `window.EVS_EVENT_API_BASE_URL`.

## API

- `GET /datasets` returns the catalog and availability notes.
- `GET /series?dataset=...&household=...` returns normalized points.
- `POST /detect` accepts `dataset`, `household`, `range_start`, `range_end`,
  `module` (`nilm` or `anomaly`) and `method`.
- `POST /evaluate` uses the same request plus `tolerance_minutes`.

Until loaders and labels are supplied, `/detect` returns an empty list and
`/evaluate` reports an unavailable ground-truth source. No labels are invented.

## Adding data

Implement `DatasetLoader` in `event_detection/data/loaders.py`. Return
`SeriesPoint` values at 15-minute resolution. Resample GridFlex's 1-minute
source there; preserve the fact that Zonnedael gas is hourly in metadata.
Register the loader in the catalog without changing the API or dashboard.

## Adding detectors

Implement `Detector` in `event_detection/nilm/base.py`, give it a unique
`name`, and register it in `detector_registry`. The API and dashboard select
methods by name, so HMM or deep-learning methods can be added without changing
the JSON contract. Anomaly detectors stay in `event_detection/anomaly/`.

## Ground truth

Evaluation is separate from detection. The current API states that no
appliance-level labels are configured. Once the datasets are inspected, add
verified labels or explicitly add synthetic events to real aggregate data and
report that source in the evaluation response.
