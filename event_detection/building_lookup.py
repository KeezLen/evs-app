"""Explicit address selection using official PDOK/BAG and optional EP-Online v5."""
from datetime import datetime, timezone
from math import isfinite
import os
import re
import httpx

LOCATION = 'https://api.pdok.nl/bzk/locatieserver/search/v3_1/free'
BAG = 'https://api.pdok.nl/kadaster/bag/ogc/v2/collections'
EP = 'https://public.ep-online.nl/api/v5/PandEnergielabel/AdresseerbaarObject/'


class LookupUnavailable(RuntimeError):
    pass


def fetch_json(url, *, params=None, headers=None):
    try:
        response = httpx.get(url, params=params, headers=headers, timeout=10, follow_redirects=False)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        # Do not echo an address, API key or upstream request URL in client errors.
        raise LookupUnavailable('The official building data service is currently unavailable.') from error


def normalize_postcode(value):
    value = re.sub(r'\s+', '', value).upper()
    if not re.fullmatch(r'[1-9][0-9]{3}[A-Z]{2}', value):
        raise ValueError('Enter a Dutch postcode, for example 1234 AB.')
    return value


def search_addresses(postcode, house_number=None):
    postcode = normalize_postcode(postcode)
    filters = ['type:adres', f'postcode:{postcode}']
    if house_number is not None:
        filters.append(f'huisnummer:{house_number}')
    response = fetch_json(LOCATION, params={'q': postcode, 'fq': filters, 'rows': 100})['response']
    addresses = []
    for row in response.get('docs', []):
        bag_id = row.get('adresseerbaarobject_id', '')
        if row.get('postcode') == postcode and re.fullmatch(r'\d{16}', bag_id):
            addresses.append({'bag_id': bag_id, 'address': row['weergavenaam'],
                              'house_number': row.get('huisnummer'), 'postcode': postcode})
    return {'addresses': addresses, 'total': response.get('numFound', len(addresses)),
            'truncated': response.get('numFound', 0) > 100, 'source': 'PDOK Locatieserver / BAG'}


def numeric(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) else None


def energy_context(bag_id):
    key = os.environ.get('EP_ONLINE_API_KEY')
    if not key:
        return {'status': 'api_key_required', 'energy_label': None,
                'note': 'Energy-label and performance data require EP_ONLINE_API_KEY on the server.'}
    try:
        rows = fetch_json(EP + bag_id, headers={'Authorization': key, 'Accept': 'application/json'})
    except LookupUnavailable:
        return {'status': 'unavailable', 'energy_label': None}
    if not isinstance(rows, list):
        return {'status': 'unavailable', 'energy_label': None}
    today = datetime.now(timezone.utc).date().isoformat()
    matches = [r for r in rows if r.get('BAGVerblijfsobjectID') == bag_id
               and str(r.get('Geldig_tot') or '')[:10] >= today]
    if not matches:
        return {'status': 'no_current_label', 'energy_label': None}
    row = max(matches, key=lambda r: str(r.get('Registratiedatum') or ''))
    label = row.get('Energieklasse')
    if label not in {'A++++', 'A+++', 'A++', 'A+', 'A', 'B', 'C', 'D', 'E', 'F', 'G'}:
        label = None
    fields = {
        'thermal_zone_area_m2': 'Gebruiksoppervlakte_thermische_zone',
        'energy_demand_kwh_m2_year': 'Energiebehoefte',
        'heat_demand_kwh_m2_year': 'Warmtebehoefte',
        'calculated_energy_kwh_m2_year': 'BerekendeEnergieverbruik',
        'primary_fossil_energy_kwh_m2_year': 'PrimaireFossieleEnergie',
        'temperature_exceedance': 'Temperatuuroverschrijding', 'compactness': 'Compactheid',
    }
    return {'status': 'available', 'energy_label': label, 'building_type': row.get('Gebouwtype'),
            'registered_at': row.get('Registratiedatum'), 'valid_until': row.get('Geldig_tot'),
            **{out: numeric(row.get(source)) for out, source in fields.items()},
            'source': 'RVO EP-Online v5',
            'note': 'Certificate calculations are not measured household consumption.'}


def lookup_building(bag_id):
    if not re.fullmatch(r'\d{16}', bag_id):
        raise ValueError('Select a valid BAG address identifier.')
    response = fetch_json(BAG + '/verblijfsobject/items', params={'identificatie': bag_id, 'limit': 2, 'f': 'json'})
    matches = [f['properties'] for f in response.get('features', [])
               if f.get('properties', {}).get('identificatie') == bag_id]
    if len(matches) != 1:
        raise ValueError('No unique building object was found for the selected address.')
    properties = matches[0]
    years = []
    warnings = []
    for link in properties.get('pand.href', []):
        # Follow only verified official BAG building UUIDs, never arbitrary upstream URLs.
        match = re.fullmatch(re.escape(BAG) + r'/pand/items/([0-9a-f-]{36})', link)
        if not match:
            continue
        try:
            building = fetch_json(BAG + '/pand/items/' + match[1], params={'f': 'json'})
            year = building.get('properties', {}).get('bouwjaar')
            if isinstance(year, int) and 1000 <= year <= 2100:
                years.append(year)
        except LookupUnavailable:
            warnings.append('Construction year temporarily unavailable.')
    energy = energy_context(bag_id)
    return {'bag_id': bag_id,
            'address': ' '.join(str(properties.get(k) or '') for k in ('openbare_ruimte_naam', 'huisnummer', 'huisletter', 'toevoeging', 'postcode', 'woonplaats_naam')).strip(),
            'floor_area_m2': numeric(properties.get('oppervlakte')),
            'building_year': years[0] if len(set(years)) == 1 else None,
            'building_years': sorted(set(years)), 'building_use': properties.get('gebruiksdoel'),
            'building_status': properties.get('status'), 'energy_label': energy['energy_label'],
            'energy_performance': energy, 'source': 'PDOK / BAG',
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'warnings': warnings,
            'note': 'Current building context; not historical metadata for an anonymous research household.'}
