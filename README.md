# Energieverdienspel — integrated demonstrator

One local service now serves the resident interface, household analysis, event
analyst view, and detector benchmark. The **Household analysis** menu entry
connects the team's shared data → household profile → daily events → existing
client-side tip catalogue and TOPSIS ranking for one selected household.

## Run locally

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m event_detection.api.main
```

On Windows use `.venv\Scripts\python.exe` instead of `.venv/bin/python`.
Open **http://127.0.0.1:8000/app** and choose **Household analysis**. No separate
static server is needed. Analyst views are at `/event_detection.html` and
`/event_benchmark.html`; API documentation is at `/docs`.

Historical household analysis is distinct from the existing simulated resident
savings/game and institutional dashboard. Events from an arbitrary research
household no longer feed advice for the simulated persona.

## Household profile fixes

- Daily, hourly and quarter-hour data now produce **daily** summaries. Complete
  interval grids are summed; partial days are not scaled to full days. A reading
  is no longer mistaken for a whole day.
- Electricity and gas are validated separately. Complete electricity survives
  a gas-only gap, including the October clock-change day.
- Missing and absent dates are reported. Duplicate timestamps, mixed resolutions,
  misaligned timestamps and timezone-aware source timestamps are rejected.
- Per-fuel readiness requires 30 complete days and 80% calendar coverage.
  These provisional thresholds describe data sufficiency, not accuracy.
- Unknown metadata stays null; conflicts are reported. Quarter-hour exports have
  no gas, so gas is unavailable rather than invented or reported as a daily gap.
- Weekday averages include sample counts; daily medians and coverage are exposed.
  Peak hours and night use are still null. Weather remains contextual; this
  descriptive profile does not train a new per-household prediction model.

## Shared product contract

`POST /product/analyze` accepts the same fields as `POST /profiles/build`:

```json
{
  "dataset": "zonnedael",
  "household": "Klant 34",
  "range_start": "2013-01-01T00:00:00",
  "range_end": "2013-03-31T00:00:00",
  "home": {"energy_label": "C", "floor_area_m2": 70}
}
```

Ranges and home details are optional. Bounds are inclusive timestamps matching
source local time, without timezone offsets. An interval end date at midnight
includes only that instant on the final day; omit the range for all history.
Empty selections and unknown households return 400; invalid ranges/context 422.

The result contains `dataset`, `profile`, `events`, `daily_series`,
`advice_context`, and `notes`, all from the same household and range. Product
rules run on daily aggregates only, independently gated per fuel by profile
readiness. This is historical pattern analysis, not a prospective forecast:
the current rules fit and describe the selected period. Advanced Isolation
Forest, RNN and benchmarks remain available through the analyst endpoints.

The client passes these events and the actual profile context to Amelia's
existing tip engine. It withholds heating-reduction tips while comfort is
unknown. It excludes tips whose ranking requires an unknown occupant count;
it does not borrow occupant details from the simulated persona. No personal
euro saving is displayed by this flow. Changing selection clears old results;
late responses cannot overwrite a newer selection.

Profile schema 0.2.0 preserves existing means, weekday patterns and home fields,
and adds data quality, readiness, sample counts and resolution provenance.
The standalone `/profiles/build` endpoint remains available with optional ranges.

## Checks

```sh
.venv/bin/python -m pytest -q
node --test tests/product.test.cjs
```

Current validation: 68 Python tests and 5 JavaScript integration tests pass.
The JavaScript harness also executes the tips component's existing assertions.
Browser checks cover full daily analysis, short-history abstention, clearing
stale results, and quarter-hour electricity-only analysis with no JavaScript
runtime errors. These are correctness checks, not model accuracy claims.

See [INTEGRATION.md](INTEGRATION.md) for remaining product work and the component
boundaries. See [event_detection/README.md](event_detection/README.md) for the
advanced detectors and benchmark tools, and
[zonnedael_data/minimum_data_list.md](zonnedael_data/minimum_data_list.md) for the
data team's required/optional inputs and consent design.
