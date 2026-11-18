Source: https://drive.google.com/file/d/1-tOtiI_bdY7eRD7grCDYdhlrdO0QeBte/view
Retrieved: 2026-11-18

# Using `GridFlex.db`

This is a SQLite database with energy data from the **GridFlex Heeten** project. It has electricity and gas readings from households in Heeten (The Netherlands). Some households also have solar panels (PV) and a home battery.

The data was made smaller. The original file has one reading per minute. This database has one value per 15 minutes (electricity) or per hour (gas).

## 1\. Source and licence

- **Original data:** Reijnders, V., Gerards, M., Hurink, J. (2021). *Energy consumption data of the GridFlex Heeten project.* Version 1\. 4TU.ResearchData. [https\://doi.org/10.4121/14447257.v1](https://doi.org/10.4121/14447257.v1)  
- **Licence:** CC BY-NC-SA 4.0 (give credit, no commercial use, share under the same licence).  
- **Period:** August 2018 to August 2020\.

## 2\. What is in the database

One table:

```
readings(timestamp INTEGER, house INTEGER, appliance INTEGER, measurement INTEGER, value REAL)
PRIMARY KEY (house, appliance, measurement, timestamp)
```

- About **62.5 million rows**. One row is one value of one series in one time interval.  
- A **series** is one combination of house, appliance and measurement. Example: house 1, SMARTMETER, IMPORT\_KW. There are about 1,130 series.  
- Names are stored as **small integers**. The lists are in section 4\. The database does not contain these lists.  
- Time range: 2018-07-31 23:00 to 2020-08-31 21:45 (UTC). In Dutch local time this is 2018-08-01 01:00 to 2020-08-31 23:45.

## 3\. How the data was changed

| Topic | What was done |
| :---- | :---- |
| Time | The original time had a UTC offset (`+02:00` or `+01:00`). It was changed to UTC and stored as **Unix seconds**. |
| Interval | `timestamp` is the **start** of the interval. Electricity: **15 minutes**. Gas (`GAS_USAGE_M3`): **60 minutes**. Intervals start on the clock (for example 12:00, 12:15). |
| One value per interval | `mean` \= average of the readings in the interval. `last` \= the last reading in the interval. |
| Where `last` is used | Counters (`*_KWH`, `GAS_USAGE_M3`), codes (`*_MODE`, `OPERATIONAL_STATE`), and `MAX_BATTERY_KW` / `MIN_BATTERY_KW`. |
| Where `mean` is used | All other measurements. |
| Missing data | Intervals without readings are **not in the table**. Nothing was filled in. |
| Number of readings | The number of readings behind each value is not stored. |
| Rounding | Values are rounded to 4 decimals. |
| Removed | 24 broken lines (of about 972 million) were removed. Nothing else was removed. |

**Small time shift.** In the original file, the time is the **end** of the one-minute interval. We grouped the readings by this time. So a row with `timestamp` 12:00 holds the minutes that ended at 12:00 to 12:14. That is the period 11:59 to 12:14. The shift is one minute. It is small, and you can usually ignore it.

## 4\. IDs and what the measurements mean

### Houses

- `House<N>` has ID **N**. Example: `House6` is 6\.  
- `HouseTest` has ID **78**. The README says it is a **dummy household** that ICT Group used to test the connection. **Leave it out of your analysis.**  
- The README says houses go from 1 to 77, but the data has **no House67**. So there are 76 real houses.

### Appliances

| ID | Name | Meaning (from the README) | Houses |
| ----: | :---- | :---- | ----: |
| 1 | BATTERY | The battery system. Not in all households. | 12 |
| 2 | PVMETER | The PV (solar) system. Not in all households. | 45 |
| 3 | SMARTMETER | The smart meter, so the whole household. | all |

### Measurements

The meanings and units come from the dataset README. `agg` tells you how the 1-minute data was combined (section 3).

| ID | Name | Appl. | Interval | agg | Unit | Meaning |
| ----: | :---- | ----: | :---- | :---- | :---- | :---- |
| 1 | BATTERY\_KW | 1 | 15 min | mean | kW | Average battery power in the last minute. **Negative \= charging**, positive \= discharging. |
| 2 | BATTERY\_TARGET\_KW | 1 | 15 min | mean | kW | The power the battery was asked to deliver. |
| 3 | BATTERY\_TARGET\_MODE | 1 | 15 min | last | code | Battery strategy. 0 \= local (battery follows `BATTERY_TARGET_KW`). 1 \= household (battery steers so that `TOTAL_KW` matches `BATTERY_TARGET_KW`). 2 \= failsafe (charge to a safe level, ignore the target). |
| 4 | CHARGE\_MODE | 1 | 15 min | last | code | What the battery may do. 0 \= idle. 1 \= charge only. 2 \= discharge only. 3 \= both. |
| 5 | CURRENT\_PHASE\_1 | 3 | 15 min | mean | A | Household current on phase 1\. Very inaccurate. Useful to see which phase a house uses. |
| 6 | CURRENT\_PHASE\_2 | 3 | 15 min | mean | A | Same, phase 2\. |
| 7 | CURRENT\_PHASE\_3 | 3 | 15 min | mean | A | Same, phase 3\. |
| 8 | EXPORT\_KW | 3 | 15 min | mean | kW | Average power the household gave to the grid in the last minute. |
| 9 | EXPORT\_KWH | 3 | 15 min | last | kWh | **Counter.** Total energy exported since the meter was connected. |
| 10 | GAS\_USAGE\_M3 | 3 | **60 min** | last | m³ | **Counter.** Total gas used since the meter was connected. |
| 11 | IMPORT\_KW | 3 | 15 min | mean | kW | Average power the household took from the grid in the last minute. |
| 12 | IMPORT\_KWH | 3 | 15 min | last | kWh | **Counter.** Total energy imported since the meter was connected. |
| 13 | MAX\_BATTERY\_KW | 1 | 15 min | last | kW | Discharge limit: the highest `BATTERY_KW` allowed. |
| 14 | MIN\_BATTERY\_KW | 1 | 15 min | last | kW | Charge limit: the lowest `BATTERY_KW` allowed (negative). |
| 15 | MOMENTARY\_EXPORT\_KW | 3 | 15 min | mean | kW | Export power at the exact moment of the reading. Slightly inaccurate. |
| 16 | MOMENTARY\_IMPORT\_KW | 3 | 15 min | mean | kW | Import power at the exact moment of the reading. Slightly inaccurate. |
| 17 | MOMENTARY\_PV\_KW | 2 | 15 min | mean | kW | PV power at the exact moment of the reading. Slightly inaccurate. |
| 18 | OPERATIONAL\_STATE | 1 | 15 min | last | code | What the battery did. 0 \= idle. 1 \= charging. 2 \= discharging. 3 \= error. |
| 19 | PV\_KW | 2 | 15 min | mean | kW | Average PV power in the last minute. **In this data, production has a negative sign.** |
| 20 | PV\_KWH | 2 | 15 min | last | kWh | **Counter.** Total PV energy since the PV system was connected to the pulse meter. |
| 21 | REQ\_CHARGE\_MODE | 1 | 15 min | last | code | The `CHARGE_MODE` that was asked from the battery. |
| 22 | STATE\_OF\_CHARGE | 1 | 15 min | mean | % | Battery charge as a percentage of its capacity. **Extremely inaccurate.** |
| 23 | TOTAL\_KW | 3 | 15 min | mean | kW | Average power use of the whole household in the last minute. **Negative \= exporting.** |
| 24 | TOTAL\_KWH | 3 | 15 min | last | kWh | **Counter.** Total energy used. Negative means more was exported than imported. |
| 25 | UNC\_KW | 3 | 15 min | mean | kW | Average power use of the household **without PV and battery**. This is the use of the household devices only. |

Notes:

- The README also lists `BATTERY_EXPORT_KW` and `BATTERY_IMPORT_KW` (total energy the battery discharged and charged). They are **not in the data**, so they are not in this database.  
- The `*_KW` values for import, export, total and PV are averages over one minute. The 15-minute mean is therefore the real average power over that time.  
- The README does not say that `PV_KW` is negative, but the data shows it. `MOMENTARY_PV_KW` is positive.  
- Start with `TOTAL_KW` for the electricity use of a whole household, and `UNC_KW` for the use of devices only.

## 5\. Data problems you should know about

These points come from the README, unless it says otherwise.

1. **Data is often missing.** Internet or server problems cause gaps. Missing readings are **not** stored as NaN or 0; they are simply absent. The authors say short gaps can be filled with linear interpolation.  
2. **Jumps in `TOTAL_KWH`.** Some values jump by more than 10 kWh in one minute. These are errors and should be thrown away. The same errors can affect other values calculated from this counter.  
3. **`UNC_KW` is not the same for all houses.** A few houses have PV but no pulse meter. For them, `UNC_KW` still contains the PV output, so it cannot be compared with `UNC_KW` of other houses.  
4. **Some values are inaccurate.** See the notes in the measurement table (`CURRENT_PHASE_*`, `STATE_OF_CHARGE`, `MOMENTARY_*`).  
5. **Not every house has every series.** Battery and PV exist only in some houses. Some series start late or stop early.  
6. **Extreme values.** A profile of the original file showed, for example, `MOMENTARY_IMPORT_KW` up to 2,020 kW, `PV_KW` down to −46 kW and `TOTAL_KWH` down to −20,656 kWh. These are not realistic for one home. Plot your data and look before you train models.

## 6\. Connecting

```py
import sqlite3
import pandas as pd

# read-only, so you cannot damage the file
con = sqlite3.connect("file:gridflex.db?mode=ro", uri=True)

APPLIANCES = {1: "BATTERY", 2: "PVMETER", 3: "SMARTMETER"}
MEASUREMENTS = {
    1: "BATTERY_KW", 2: "BATTERY_TARGET_KW", 3: "BATTERY_TARGET_MODE", 4: "CHARGE_MODE",
    5: "CURRENT_PHASE_1", 6: "CURRENT_PHASE_2", 7: "CURRENT_PHASE_3", 8: "EXPORT_KW",
    9: "EXPORT_KWH", 10: "GAS_USAGE_M3", 11: "IMPORT_KW", 12: "IMPORT_KWH",
    13: "MAX_BATTERY_KW", 14: "MIN_BATTERY_KW", 15: "MOMENTARY_EXPORT_KW",
    16: "MOMENTARY_IMPORT_KW", 17: "MOMENTARY_PV_KW", 18: "OPERATIONAL_STATE",
    19: "PV_KW", 20: "PV_KWH", 21: "REQ_CHARGE_MODE", 22: "STATE_OF_CHARGE",
    23: "TOTAL_KW", 24: "TOTAL_KWH", 25: "UNC_KW",
}
BATTERY_IDS = {1, 2, 3, 4, 13, 14, 18, 21, 22}
PV_IDS = {17, 19, 20}

def appliance_of(m):               # which appliance ID belongs to a measurement ID
    return 1 if m in BATTERY_IDS else 2 if m in PV_IDS else 3
```

7\. Examples

### Which series does a house have?

```py
pd.read_sql_query(
    "SELECT DISTINCT appliance, measurement FROM readings WHERE house = ?", con, params=(1,)
).assign(name=lambda d: d.measurement.map(MEASUREMENTS))
```

### Load one series

```py
def load(house, measurement):
    df = pd.read_sql_query(
        "SELECT timestamp, value FROM readings "
        "WHERE house = ? AND appliance = ? AND measurement = ? ORDER BY timestamp",
        con, params=(house, appliance_of(measurement), measurement))
    df["time"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)   # UTC
    return df.set_index("time")["value"]

total_kw = load(1, 23)                               # TOTAL_KW of house 1
local = total_kw.tz_convert("Europe/Amsterdam")      # Dutch local time
```

### One house as a wide table (one column per measurement)

```py
df = pd.read_sql_query(
    "SELECT timestamp, measurement, value FROM readings WHERE house = ? AND appliance = 3",
    con, params=(1,))
wide = df.pivot(index="timestamp", columns="measurement", values="value").rename(columns=MEASUREMENTS)
wide.index = pd.to_datetime(wide.index, unit="s", utc=True)
```

Gas has only hourly values. So `GAS_USAGE_M3` is empty (NaN) between the full hours.

### The same measurement for many houses

Use one query per house. This is fast (see section 8).

```py
frames = []
for h in range(1, 78):                     # House IDs 1..77 (leave out 78 = HouseTest, 67 does not exist)
    d = pd.read_sql_query(
        "SELECT timestamp, value FROM readings WHERE house = ? AND appliance = 3 AND measurement = 23",
        con, params=(h,))
    if not d.empty:
        frames.append(d.assign(house=h))
all_total = pd.concat(frames)
```

### Energy per interval

Power is an average, so for 15-minute rows: energy in kWh \= power in kW × 0.25.

```py
import_kwh_per_interval = load(1, 11) * 0.25      # IMPORT_KW -> kWh in each 15 minutes
```

### Use per interval from a counter (`*_KWH`, `GAS_USAGE_M3`)

Counters hold the meter reading. Take the difference between rows. Remove differences that cross a gap, and remove errors.

```py
s = load(1, 12)                                   # IMPORT_KWH, 15-minute rows
used = s.diff()
used[s.index.to_series().diff() != pd.Timedelta("15min")] = float("nan")   # there is a gap
used[(used < 0) | (used > 10)] = float("nan")     # negative or > 10 kWh in 15 min = error
# For gas use "60min", and do not use the "> 10" rule.
```

The same in SQL (needs SQLite 3.25 or newer):

```sql
SELECT timestamp, value - LAG(value) OVER (ORDER BY timestamp) AS used
FROM readings WHERE house = 1 AND appliance = 3 AND measurement = 12
ORDER BY timestamp;
```

### Fill short gaps

```py
s = load(1, 23)
full = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="15min"))
filled = full.interpolate(method="time", limit=4)   # fills gaps of up to 1 hour
```

&nbsp;
