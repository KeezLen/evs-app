"""Compose shared data, profiles and baseline events for one household selection."""
from math import isfinite
from event_detection.household_profile import build_profile, daily_points, valid
from event_detection.nilm.rules import RuleBasedDetector


def analyze_household(points, household, home):
    profile = build_profile(points, household, home)
    daily = daily_points(points)
    detection_points = []
    for point in daily:
        values = {fuel: getattr(point, fuel) if valid(point, fuel)
                  and profile['fuels'][fuel]['status'] == 'ready' else None
                  for fuel in ('electricity_kwh', 'gas_m3')}
        hdd = point.hdd18
        detection_points.append(point.model_copy(update={
            **values, 'quality_flag': 'ok' if any(v is not None for v in values.values()) else 'missing',
            'hdd18': hdd if hdd is not None and isfinite(hdd) and hdd >= 0 else None,
        }))
    events = RuleBasedDetector().detect(detection_points)
    return {
        'profile': profile, 'events': events, 'daily_series': daily,
        'advice_context': {
            'household_id': household, 'home': profile['home'],
            'season': profile['seasons'][0] if len(profile['seasons']) == 1 else None,
            'comfort_assessed': False, 'allow_heating_reduction': False,
            'validated_predictions': False,
        },
        'notes': ['Historical demonstration: rules describe this selected period, not prospective forecasts.',
                  'Tip ranking uses the existing client-side catalogue; heating-reduction tips are withheld because comfort is unknown.',
                  'Savings and game progress remain simulated and are not calculated from this household.'],
    }
