"""Read-only daily adapter for the team's resampled GridFlex SQLite database."""
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from math import isfinite
import os
from pathlib import Path
import re
import sqlite3
from zoneinfo import ZoneInfo

from event_detection.schemas import SeriesPoint

AMSTERDAM = ZoneInfo('Europe/Amsterdam')
DEFAULT_PATH = Path(__file__).resolve().parents[2] / 'local_data/gridflex/gridflex.db'
# Provisional safety screen, matching the team's 10 kWh/quarter-hour example.
MAX_IMPORT_KW = 40


class GridFlexLoader:
    dataset_id = 'gridflex_heeten'

    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('GRIDFLEX_DB_PATH', DEFAULT_PATH)).expanduser().resolve()

    def connect(self):
        if not self.path.is_file():
            raise FileNotFoundError('GridFlex database is not configured; set GRIDFLEX_DB_PATH.')
        con = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
        con.execute('PRAGMA query_only=ON')
        return con

    @property
    def available(self):
        return self.path.is_file()

    @property
    def included_households(self):
        if not self.available:
            return set()
        return set(self._households(self.path.stat().st_mtime_ns))

    @lru_cache(maxsize=2)
    def _households(self, modified):
        del modified
        houses, last = [], 0
        with closing(self.connect()) as con:
            # Seek the primary key instead of scanning all 62.5 million rows.
            while True:
                row = con.execute('SELECT house FROM readings WHERE house > ? ORDER BY house LIMIT 1', (last,)).fetchone()
                if row is None:
                    break
                last = row[0]
                if 1 <= last <= 77:
                    houses.append(f'House{last}')
        return tuple(houses)

    def load(self, household):
        match = re.fullmatch(r'House([1-9][0-9]?)', household)
        if not match or household not in self.included_households:
            raise ValueError('Select an available GridFlex household; HouseTest is excluded.')
        return [p.model_copy(deep=True) for p in self._daily(int(match[1]), self.path.stat().st_mtime_ns)]

    @lru_cache(maxsize=8)
    def _daily(self, house, modified):
        del modified
        channels = {}
        with closing(self.connect()) as con:
            for measurement in (8, 10, 11):
                channels[measurement] = con.execute(
                    'SELECT timestamp, value FROM readings WHERE house=? AND appliance=3 AND measurement=? ORDER BY timestamp',
                    (house, measurement)).fetchall()
        if not channels[11] and not channels[10]:
            raise ValueError('No import or gas readings for this GridFlex household.')
        days = defaultdict(lambda: {'imports': {}, 'exports': {}, 'gas': {}})
        for measurement, name in ((11, 'imports'), (8, 'exports')):
            for stamp, value in channels[measurement]:
                # Preserve export as a separate channel, never treat signed TOTAL_KW as load.
                local = datetime.fromtimestamp(stamp, timezone.utc).astimezone(AMSTERDAM)
                bucket = days[local.date()][name]
                if stamp % 900 == 0 and isfinite(value) and 0 <= value <= MAX_IMPORT_KW:
                    bucket[stamp] = value*0.25
        previous = None
        for stamp, value in channels[10]:
            # Counter is the last observation within the labelled hour. Attribute its
            # difference to the current hourly bin; never spread a difference across gaps.
            if previous is not None:
                prior_stamp, prior_value = previous
                interval_start = stamp
                local_day = datetime.fromtimestamp(interval_start, timezone.utc).astimezone(AMSTERDAM).date()
                days[local_day]  # Preserve the day even for an invalid difference.
                difference = value-prior_value
                if stamp % 3600 == 0 and stamp-prior_stamp == 3600 and isfinite(difference) and difference >= 0:
                    days[local_day]['gas'][interval_start] = difference
            previous = (stamp, value)
        if not days:
            raise ValueError('No usable GridFlex dates.')
        notes = [
            'Electricity is grid import (IMPORT_KW × 0.25), not total household device consumption.',
            'Export is separate; solar/battery homes are retained without inferring solar from net signs.',
            'Source minute counts were not retained; a full aggregate grid does not prove complete raw minutes.',
            'Gas is adjacent hourly counter differences; gaps and negative resets are excluded.',
            'Gas last-in-bin counter differences approximate the labelled hour; original minute timestamps are unavailable.',
            'Import/export power outside 0–40 kW is excluded by a provisional demo quality screen.',
            'No weather joined: gas pattern classification and weather-based gas events abstain.',
        ]
        result = []
        start, end = min(days), max(days)
        day = start
        while day <= end:
            data = days[day]
            midnight = datetime.combine(day, time(), AMSTERDAM)
            next_midnight = datetime.combine(day+timedelta(days=1), time(), AMSTERDAM)
            hours = int((next_midnight.timestamp()-midnight.timestamp())/3600)
            expected_e = hours*4
            first = int(midnight.timestamp())
            # Membership checks enforce coverage and protect against off-grid bins.
            imports = {t:v for t,v in data['imports'].items() if first <= t < int(next_midnight.timestamp())}
            gas = data['gas']
            e_full, g_full = len(imports) == expected_e, len(gas) == hours
            e = sum(imports.values()) if e_full else None
            g = sum(gas.values()) if g_full else None
            exports = data['exports']
            quality = 'ok' if e_full and g_full else 'partial' if imports or gas else 'missing'
            result.append(SeriesPoint(timestamp=datetime.combine(day, time()),
                electricity_kwh=e, gas_m3=g, quality_flag=quality,
                n_elec_intervals=len(imports), n_gas_hours=len(gas),
                expected_elec_intervals=expected_e, expected_gas_hours=hours,
                electricity_basis='grid_import', electricity_export_kwh=sum(exports.values()) if len(exports) == expected_e else None,
                source_notes=notes))
            day += timedelta(days=1)
        return tuple(result)
