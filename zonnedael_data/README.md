# Zonnedael data

Here's the data for the demo. The weather is already joined in, so you don't need to do anything with the KNMI files.

## What's in here

zonnedael_daily_weather.csv is the main file. It has one row per household per day: 58 homes, all of 2013, 21,170 rows. The data is daily and comes in the next day (T+1).

household_summary.csv lists every home, whether it was kept, and why not if it wasn't (solar panels, almost no gas, too many gaps).

scenarios/ has four small test files for one home (Klant 34, Jan-Mar 2013). They're good for testing your stuff. The README in there explains them.

data_note_zonnedael.md has the background, if you want to know where the data comes from and what was changed.

## Columns

| Column | What it is |
|---|---|
| household_id | Anonymous home code, like Klant 34 |
| date | YYYY-MM-DD |
| electricity_kwh | Electricity used that day, in kWh. Can be empty |
| gas_m3 | Gas used that day, in m³. Can be empty |
| n_elec_intervals | How many quarter-hours came in (96 = full day) |
| n_gas_hours | How many hours came in (24 = full day) |
| quality_flag | ok, partial (some data came in) or missing (none came in) |
| woning_type, bouwjaar_band, gezinssituatie | House type, build year, household type. Empty for about half the homes |
| temp_mean_c, temp_min_c, temp_max_c | Temperature that day in °C (KNMI De Bilt) |
| hdd18 | Heating degree days: how far the mean temp was below 18 °C |

## Watch out for

Empty means the data didn't come in, not zero use. Check quality_flag, and don't count those days as weird use.

Compare gas with the temperature or hdd18. Cold days use more gas, and that's normal.

Your code should still work when the house columns are empty. incomplete.csv tests this.

27 October 2013 is partial for every home. 2 gas hours are missing that day (the clocks went back). It's a data thing, not behaviour.

Klant 58 uses no gas at all from August to December, while its electricity stays normal. It probably stopped heating with gas, or the gas meter was cut off. Its winter days at the end of 2013 will look like "no heating". Leave it out of gas work after July, or treat it on purpose as a test case.

Klant 71 is an extreme home: a big detached house from before 1940. It uses about 11,000 kWh of electricity a year (more than 3 times the median) and sometimes 6-8 m³ of gas in one hour, even in summer (normal is under 2). The values look real, not like errors, but they can dominate anything that compares homes or looks for spikes.

Both homes are still in the files. Nothing was removed or changed.

## Hourly and 15-minute files

These come from the same raw Liander data and the same 58 homes as the daily file.

zonnedael_hourly.csv.gz has electricity, gas and temperature per hour: 508,080 rows. Columns: household_id, timestamp, electricity_kwh, gas_m3, n_elec_intervals (quarter-hours that came in, 4 = full hour), quality_flag, temp_c (KNMI De Bilt, hourly).

zonnedael_15min_electricity.csv.gz has electricity per quarter-hour: 2,032,320 rows. Columns: household_id, timestamp, electricity_kwh, quality_flag. Gas isn't in it, because gas only exists per hour.

pandas reads both directly: pd.read_csv("zonnedael_hourly.csv.gz").

Things to know:

The timestamp is the start of the hour or quarter, in Dutch winter time (UTC+1) all year. Liander's timestamps have no summer-time jumps, so there's no shift in March or October.

Hours and days add up exactly to the daily file, so the three files agree with each other.

Gas per hour follows the thermostat more than the weather: peaks around 08:00 and 18:00, little at night. Per day, gas and temperature line up well, but per hour you also need the time of day.

15 minutes is coarse for spotting single appliances. Expect general patterns (evening peak, base load, unusual days) more than "this was the washing machine".
