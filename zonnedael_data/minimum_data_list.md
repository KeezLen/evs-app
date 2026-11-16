# Minimum data list

This lists every piece of data the Energieverdienspel app uses. The core is the household profile, event detection and tips. It runs on daily meter data that arrives the next day (T+1), plus weather. It needs no input from the tenant. Everything marked optional may be empty, and the core must still work then.

Meter data about a household counts as personal data, even when it is stored under a code instead of a name. The data can be traced back to a home and its residents.

"Optional: No" means the core needs that item for the part of the app that uses it. The tenant can still choose not to share it. The section on data rights says what happens then.

## Meter readings

| Data | Source | Why it is needed | Optional | Personal data |
|---|---|---|---|---|
| Household ID | App, a code per home | Links all data of one home together. | No | Yes |
| Date | Meter data | Each value belongs to one day. Weather is joined on it. | No | Yes, as part of the reading |
| Electricity use per day (kWh) | Smart meter, T+1 | Base for the electricity profile, events and tips. | No | Yes |
| Gas use per day (m³) | Smart meter, T+1 | Base for the heating profile, events and tips. Gas is the largest cost in most homes. | No | Yes |
| Number of gas hours per day | Counted from the meter data | Shows whether the gas total covers the whole day. | No | Yes |
| Number of electricity intervals per day | Counted from the meter data | Shows whether the electricity total covers the whole day. | No | Yes |
| Quality flag (ok, partial, missing) | Worked out from the two counts | Keeps data problems apart from unusual use. A day with missing data is never shown as low or high use. | No | Yes |

## Weather

| Data | Source | Why it is needed | Optional | Personal data |
|---|---|---|---|---|
| Mean temperature per day (°C) | KNMI daily data | Gas use depends mostly on outdoor temperature. Without it a cold day looks like waste. | No | No |
| Minimum and maximum temperature per day (°C) | KNMI daily data | Helps explain a cold night or a mild afternoon. The core can work without them. | Yes | No |
| Heating degree days (HDD, base 18 °C) | Worked out from mean temperature | Makes gas use comparable across days with different weather. | No | No |

The demo uses station 260 (De Bilt), because Zonnedael is not a real place. The real app uses one fixed station for the whole area. It does not need the tenant's address for weather.

## Building information

| Data | Source | Why it is needed | Optional | Personal data |
|---|---|---|---|---|
| Address | Tenant or housing association | Only used to look up the BAG ID. It is not needed for anything else. | Yes | Yes |
| BAG ID | BAG, found with the address | Links the home to public building data such as build year and floor area. | Yes | Yes, it points to one home |
| House type (woning_type) | BAG or the tenant | Makes it possible to compare a home with similar homes. | Yes | Yes, when linked to the household |
| Build year band (bouwjaar_band) | BAG | Older homes lose more heat, so the same gas use can mean something different. | Yes | Yes, when linked to the household |
| Floor area (m²) | BAG | A bigger home needs more heat, so expected gas use depends on it. The model of expected use takes it as an input. | Yes | Yes, when linked to the household |
| Energy label | EP-Online, found with the BAG ID | Gives a rough idea of insulation. It helps choose tips that fit the home. | Yes | Yes, when linked to the household |

## Input from the tenant

| Data | Source | Why it is needed | Optional | Personal data |
|---|---|---|---|---|
| Household situation (gezinssituatie) | Tenant | Explains differences in use, for example a family uses more hot water than one person. | Yes | Yes |
| Schedules (when people are home) | Tenant | Helps time tips, for example about heating when nobody is home. | Yes | Yes |

## What happens when optional data is empty

The core only needs the required items. All of them come from the meter and from KNMI. The tenant does not have to enter anything. Without building information or tenant input, the profile only compares a home with its own history and with the weather. Tips then stay general. Tips must never push a tenant to heat less than they need, with or without optional data.

## Data rights

The tenant decides what they share, and can change that at any time. Consent is asked per group of data: electricity, gas, building information and input from the tenant. The counts and the quality flag belong to their meter data and follow the same consent. The address is only asked for when the tenant shares building information. Weather is not personal data and needs no consent.

| Situation | What the app does | What happens to the data |
|---|---|---|
| The tenant shares some groups but not all | The core runs on what is shared. For example, with electricity but no gas there is no heating profile and no gas tips. Everything else works. | Groups that are not shared are never collected. |
| The tenant shares no meter data | There is no profile and no event detection. The app can only show general tips. | Nothing personal is collected. |
| The tenant withdraws consent for one group | The app stops using that group and carries on with the rest. | Collection of that group stops from the next day. Stored data of that group is deleted. |
| The tenant withdraws all consent | The app stops working for this home. | Collection stops. All personal data of the household is deleted. |
| The tenant asks to delete their data but keeps using the app | The profile starts again from empty, as in the incomplete scenario. | All stored history is deleted. New data is only collected while consent stays on. |

Partial sharing uses the same rule as empty optional data. The core works with whatever it has and never guesses what is missing.

Two points are still open and need to be agreed with the company. The first is how quickly data must be deleted after a request. The second is whether anonymous totals, for example for the impact dashboard, may be kept after a tenant has left. The consent screens must use the same groups and the same wording as this section.
