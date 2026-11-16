# Recent weather

Daily temperature for Heerlen for the last 14 days, today included. It's the same kind of weather as in the Zonnedael file, so the same code can use it.

## Columns

| Column | What it is |
|---|---|
| date | YYYY-MM-DD |
| temp_mean_c, temp_min_c, temp_max_c | Temperature that day in °C |
| hdd18 | Heating degree days: how far the mean temp was below 18 °C |
| source | knmi_380 (measured at KNMI Beek) or open_meteo (model estimate for Heerlen) |
| is_today | True for today's row |

## Where it comes from

KNMI station 380 (Beek) is the main source. It's the closest KNMI station to Heerlen-Noord, about 15 km away.

KNMI only publishes a day after it's over, and usually with a delay of a day or two. Those last days come from Open-Meteo, a free weather service. When KNMI catches up, its values replace the Open-Meteo ones on the next run.

Today's row is not final. Part of the day hasn't happened yet, so it's partly a forecast. Use it for things like "it's cold today", not for judging today's gas use.

## How close Open-Meteo is

Compared with KNMI Beek over 29 days in October 2026, Open-Meteo was on average 0.4 °C warmer for the mean temperature, at most 1.4 °C off. The minimum temperature is less exact (up to 2.7 °C off). For hdd18 and gas this is close enough. For final numbers, use the KNMI rows.

## Licence

KNMI data is open (CC BY 4.0). Open-Meteo data is CC BY 4.0 too. Credit both: "Weather data: KNMI and Open-Meteo.com".

## Watch out for

This file is a snapshot from 2 November 2026. In the real app the backend has to fetch it again every day.

Zonnedael uses De Bilt (260), because Zonnedael isn't a real place. This file is for Heerlen, so it uses Beek.
