"""Explainable descriptive labels, not efficiency or behavioural diagnoses."""
from statistics import mean, pstdev, median
from math import isfinite

POLICY = {
    'version': '1.0', 'validated': False, 'minimum_days': 30,
    'minimum_coverage': 0.8, 'steady_cv_max': 0.15, 'high_variance_cv_min': 0.35,
    'weekday_weekend_difference_min': 0.20,
}


def pattern_labels(points, fuel, summary):
    """CV = population standard deviation / mean; gas is weather-adjusted first."""
    # Import here to avoid a dependency cycle with the profile builder.
    from event_detection.household_profile import valid
    good = [p for p in points if valid(p, fuel)]
    result = {'labels': [], 'metrics': {}, 'policy': POLICY.copy(), 'basis': 'daily_totals'}
    if summary['status'] != 'ready':
        result['labels'] = [{'code': summary['status'], 'reason': 'Not enough complete, observed days for pattern labels.'}]
        return result
    values = [getattr(p, fuel) for p in good]
    average = mean(values)
    if average == 0:
        result['labels'] = [{'code': 'no_recorded_use', 'reason': 'All complete observed daily totals are zero; no cause is inferred.'}]
        return result
    result['metrics']['raw_daily_cv'] = pstdev(values)/average
    residuals = values
    if fuel == 'gas_m3':
        weather = [p for p in good if p.hdd18 is not None and isfinite(p.hdd18) and p.hdd18 >= 0]
        if len(weather) < POLICY['minimum_days'] or len(weather)/len(good) < 0.8 or max(p.hdd18 for p in weather)-min(p.hdd18 for p in weather) < 5:
            result['labels'] = [{'code': 'weather_context_needed', 'reason': 'Gas variability is not classified without sufficient weather coverage and variation.'}]
            return result
        # A deterministic bounded sample prevents quadratic work on long histories.
        sample = weather[::max(1, (len(weather)+179)//180)]
        slopes = [(b.gas_m3-a.gas_m3)/(b.hdd18-a.hdd18) for i,a in enumerate(sample)
                  for b in sample[i+1:] if abs(b.hdd18-a.hdd18) >= 1]
        if not slopes:
            result['labels'] = [{'code': 'weather_context_needed', 'reason': 'Insufficient independent weather values.'}]
            return result
        slope = max(0.0, median(slopes))
        intercept = median(p.gas_m3-slope*p.hdd18 for p in weather)
        residuals = [p.gas_m3-max(0, intercept+slope*p.hdd18) for p in weather]
        average = mean(p.gas_m3 for p in weather)
        result['basis'] = 'weather_adjusted_residuals'
        result['metrics'].update({'weather_days': len(weather), 'weather_slope_m3_per_hdd18': slope})
    if average == 0:
        return result
    cv = pstdev(residuals)/average
    code = 'steady_pattern' if cv <= POLICY['steady_cv_max'] else 'high_variance' if cv >= POLICY['high_variance_cv_min'] else 'variable_pattern'
    result['metrics']['classification_cv'] = cv
    result['labels'].append({'code': code, 'reason': f'{result["basis"]}: relative variability {cv:.3f}; steady <= 0.15, high >= 0.35.'})
    if fuel == 'electricity_kwh':
        weekdays = [p.electricity_kwh for p in good if p.timestamp.weekday() < 5]
        weekends = [p.electricity_kwh for p in good if p.timestamp.weekday() >= 5]
        if len(weekdays) >= 20 and len(weekends) >= 8 and mean(weekdays) > 0:
            difference = (mean(weekends)-mean(weekdays))/mean(weekdays)
            result['metrics']['weekend_vs_weekday_fraction'] = difference
            if abs(difference) >= POLICY['weekday_weekend_difference_min']:
                result['labels'].append({'code': 'weekend_higher' if difference > 0 else 'weekday_higher',
                    'reason': f'Weekend mean differs from weekday mean by {difference:.1%}; threshold is 20%.'})
    return result
