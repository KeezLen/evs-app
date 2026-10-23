# evs-app

The resident prototype is in [index.html](index.html). Event detection is a
separate, data-ready FastAPI service in [event_detection](event_detection/).
See [event_detection/README.md](event_detection/README.md) for setup and the
JSON API contract.
## Household profile prototype

Open **Profile → Build profile from meter data**. Start the API using the
[event detection setup](event_detection/README.md), and serve `index.html` with
`python3 -m http.server 8080` (open http://localhost:8080).

The builder uses the existing `/datasets` catalog and `get_series` loader,
including the data team's included-household list. `POST /profiles/build`
accepts `dataset`, `household`, and optional `home` fields: `energy_label`,
`floor_area_m2`, `work_schedule`, and `sleep_schedule`.

Following the project plan's prototype scope (§1.6), the returned profile
contains daily electricity/gas averages, weekday patterns, highest-use weekdays,
and household context for downstream tip selection. Missing or incomplete fuel
totals are excluded separately. Peak hours and night consumption remain null
because the supplied data is daily. No separate per-household model is trained.
The simulated game and its tip selection remain separate from this profile API.

Run checks: `.venv/bin/python -m pytest -q`.
