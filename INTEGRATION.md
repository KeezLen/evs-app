# Product integration handoff

## Combined locally

Integration branch: `integration/household-product`.

- Latest `main` includes the tips branch through merge #2 (`09841bd`).
- `origin/eventdetection` supplies updated data loaders, hourly/quarter-hour
  exports, Isolation Forest, RNN, and analyst view (`1155606`).
- `origin/detectorbenchmark` supplies newer detector fixes, benchmark protocols,
  weather audits and saved results (`beb5c7e`).
- The data branch's minimum data list and recent weather sample are copied
  explicitly. Its older frontend is not used to replace the integrated UI.
  The recent-weather sample is retained as a team asset, not silently joined to
  the 2013 research data or used as a live forecast.

These changes are local; no remote branch, main update or deployment is implied.

## Working first product slice

1. Open `/app` → Household analysis.
2. Choose dataset, household and optional period/home information.
3. `/product/analyze` loads the normalized source once for that request.
4. The profile aggregates to complete days and describes quality/readiness.
5. The daily rules see only usable readings from fuels with enough history.
6. The response feeds the existing tip catalogue and TOPSIS ranking using that
   household's known energy label and event season. The newest eligible event
   supplies the trigger. Unknown comfort blocks heating-reduction tips.
7. Results show profile, quality, patterns and a tip together. They do not change
   the simulated savings, rewards, persona or stored consent settings.

The product's profile and detector work from the same daily series. The rules
still compute their own descriptive median/weather baseline; the profile is
not a trained expected-use model. An anomaly is not an appliance attribution or
proof of avoidable waste. Current readiness and detector thresholds require
validation before tenant-facing use.

## Next product increments, in order

1. **Agree and freeze contracts.** George/Sophia own profile quality/readiness;
   Keez owns event types, direction, baseline provenance and detector validation;
   Amelia owns tip applicability/ranking and exposure records; Team Data owns
   normalization, quality semantics and required inputs. Confirm field names,
   schema version, units and missing-value behaviour together.
2. **Validate prediction and event suitability.** Use chronological holdouts,
   held-out households and seasons; compare with naive baselines. Record errors,
   coverage/abstention and calibrated uncertainty separately per fuel. The earlier
   small gas check did not beat a flat baseline. Do not claim the research KPI
   or a meaningful comfort threshold has been established.
3. **Extend the product's detector adapter.** The initial flow deliberately uses
   daily rules; advanced Isolation Forest/RNN are in the analyst view. Introduce
   a stable event contract (fuel, direction, unit, baseline, quality and period)
   before mapping their generic unusual-use events to tips. A low-use anomaly
   must never be treated as high use.
4. **Replace simulated savings with evaluated results.** Build one shared,
   tested tariff/cost function using explicit tariffs and a validated normal-use
   baseline. Track period, model version and uncertainty. Only then connect
   savings, comfort eligibility, rewards and the resident home screen to the
   selected household. Do not present catalogue savings estimates as measured
   personal savings.
5. **Persist the chosen context and tip exposures.** Move the chosen dataset,
   household and range into shared app state, with invalidation on switch.
   Persist actual tip exposures with rule version, event/input provenance and
   deduplication; console logging is not durable audit logging. Establish an API
   or shared module for tip ranking if multiple clients need it. Optional
   household size must stay unknown until explicitly supplied.
6. **Prepare the pilot boundary.** Add authenticated household selection,
   consent by data group, deletion/revocation behaviour, bounded/cached loading,
   background jobs for expensive models, dependency locking, configuration and
   deployment. The local research selector is not an authenticated tenant portal.
7. **Run a complete journey acceptance test.** Test complete data, short history,
   gas-only/electricity-only sharing, gaps, unknown house details, cold weather,
   below-baseline use, household switching, API failure and consent withdrawal.
   Results, tips and savings must all refer to the same household and period.

## Known technical boundaries

- Sources use naive local timestamps. A day must match the nominal 24-hour grid;
  clock-change ambiguity is excluded rather than imputed. Correct timezone-aware
  DST handling requires timestamp offsets from the data pipeline.
- Leading/trailing missing days outside the first/last recorded dates cannot be
  inferred without an expected observation window or enrollment date.
- Interval exports do not carry the daily file's house metadata. Missing metadata
  stays unknown; a future canonical household-context source should join by ID.
- GridFlex is listed but its adapter remains unavailable.
- The local service still exposes the existing permissive development CORS and
  research data access. Pilot access controls are unfinished.
