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
  Peak hours and night use are still null. A descriptive weather adjustment is
  used for gas pattern labels; this is not a validated prediction model.

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

Profile schema 0.3.0 preserves existing means, weekday patterns and home fields,
and adds data quality, readiness, sample counts and resolution provenance.
The standalone `/profiles/build` endpoint remains available with optional ranges.

## Checks

```sh
.venv/bin/python -m pytest -q
node --test tests/product.test.cjs
```

Current validation: 89 Python tests and 5 JavaScript integration tests pass.
The JavaScript harness also executes the tips component's existing assertions.
Browser checks cover full daily analysis, short-history abstention, clearing
stale results, and quarter-hour electricity-only analysis with no JavaScript
runtime errors. These are correctness checks, not model accuracy claims.

See [INTEGRATION.md](INTEGRATION.md) for remaining product work and the component
boundaries. See [event_detection/README.md](event_detection/README.md) for the
advanced detectors and benchmark tools, and
[zonnedael_data/minimum_data_list.md](zonnedael_data/minimum_data_list.md) for the
data team's required/optional inputs and consent design.


## GridFlex database and pattern labels (18 November)

The local database is `local_data/gridflex/gridflex.db` (1,544,912,896 bytes;
62,533,683 readings). It is excluded from Git. For another machine, download the
[team database](https://drive.google.com/file/d/1ek8nDKnghBds4xGPV1C84nbuc1148ccf/view)
to that path, or set `GRIDFLEX_DB_PATH` to its location **before starting** the
service. See [the verified manifest](docs/research/gridflex_manifest.json),
[conversion notes](docs/research/usage.md) and
[original source notes](docs/research/original_readme.md). All 76 real homes are
available; HouseTest is excluded. Availability is detected at runtime, so team
members without the database can still use Zonnedael.

The GridFlex adapter returns daily **grid import**, using IMPORT_KW × 0.25 per
quarter-hour. Export remains separate. Neither signed net exchange nor import
is represented as total household device consumption. Solar/battery homes are
not excluded based on sign alone. Gas uses adjacent counter differences in the
labelled hour; gaps and negative resets are excluded without filling. Daily
coverage follows actual Amsterdam days, including 23/25-hour DST days. The
source did not retain minute counts, so complete aggregate grids do not prove
complete raw measurements. Import/export values outside 0–40 kW are excluded
by a provisional quality screen requiring validation.

Each fuel now has `patterns.labels`, `patterns.metrics`, `patterns.basis` and a
versioned, explicitly unvalidated `patterns.policy`. With at least 30 complete
days and 80% coverage, daily relative variability is standard deviation divided
by mean: at most 0.15 → steady pattern; at least 0.35 → high variance; otherwise
variable pattern. Electricity also labels weekday/weekend differences of at
least 20%, with at least 20 weekdays and 8 weekend days. All-zero observations
are labelled no recorded use without inferring a cause.

Gas is classified on residual variation after a robust heating-degree-day
adjustment, requiring at least 30 weather days, 80% weather coverage and 5 HDD
of variation. GridFlex currently has no joined weather, so its gas labels say
weather context needed, and gas event rules abstain. These labels describe the
chosen fuel, period and channel; they do not label a resident as wasteful or a
building as inefficient.

The 76-home GridFlex audit found 41 high-variance import profiles, 22 variable
profiles and 13 with insufficient history/coverage. Twelve also show higher
weekend import. None met the steady threshold in this dataset; thresholds were
not adjusted to force all categories to appear. Generation and batteries can
influence grid-import variability. These are descriptive results, not validated
behavioural or solar classifications.

## Postcode → exact address → building context

The Household analysis screen includes an optional postcode search, optional
house number, explicit address selection, and a confirmation checkbox before
using the details for the selected household. Changing the household removes
automatically applied details and clears the result. A postcode alone never
selects a house automatically. Anonymous research homes have no verified
address link; do not link a real address unless you know it is the same home.

- `POST /homes/search`: `{"postcode":"1234 AB","house_number":12}`; the number
  is optional. Returns address candidates with BAG IDs, a total and truncation
  indicator. A truncated postcode search can be narrowed with house number.
- `POST /homes/lookup`: `{"bag_id":"<16 digits>"}`. Returns BAG floor area,
  linked building year(s), registered use/status, provenance and optional
  EP-Online certificate data. No house type is guessed from registered use.
- `/profiles/build` and `/product/analyze` optionally accept `building_bag_id`
  and `building_confirmed:true`. The server retrieves the selected record;
  explicit manual floor area/energy label take priority over lookup values.

PDOK/BAG address and building lookup works without a key. To enable energy
labels, building type, certificate energy/heat demand, calculated energy use,
compactness and temperature exceedance, configure `EP_ONLINE_API_KEY` in the
server environment. No key is included in the repository or sent to the browser.
With no key, a missing/expired certificate, or a service failure, those fields
remain unknown. Thermal-zone area is kept distinct from BAG floor area; energy
performance figures in kWh/m²/year are not measured meter usage or savings.
Addresses are used transiently, not persisted to app storage by this feature.
This does not replace pilot authentication and consent enforcement.

Official API references:
[PDOK Locatieserver](https://www.pdok.nl/pdok-locatieserver),
[BAG OGC API](https://api.pdok.nl/kadaster/bag/ogc/v2),
[EP-Online v5 specification](https://public.ep-online.nl/swagger/v5/swagger.json),
[EP-Online key application](https://apikey.ep-online.nl/).
Current research text snapshots are in `docs/research/`; original revised Word
files downloaded locally are in `local_data/research/` and are not committed.
