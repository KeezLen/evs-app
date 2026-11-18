from datetime import datetime, timedelta, timezone
import sqlite3
from zoneinfo import ZoneInfo
import pytest
from event_detection.data.gridflex import GridFlexLoader
from event_detection.household_profile import build_profile, valid


def database(tmp_path, start='2019-01-01', days=2, missing_e=False, gas_reset=False):
    path=tmp_path/'test.db'
    con=sqlite3.connect(path)
    con.execute('CREATE TABLE readings(timestamp INTEGER, house INTEGER, appliance INTEGER, measurement INTEGER, value REAL, PRIMARY KEY(house,appliance,measurement,timestamp)) WITHOUT ROWID')
    zone=ZoneInfo('Europe/Amsterdam')
    first=datetime.fromisoformat(start).replace(tzinfo=zone)
    last=first+timedelta(days=days)
    stamps=range(int(first.timestamp()),int(last.timestamp()),900)
    for i,stamp in enumerate(stamps):
        if not (missing_e and i==3): con.execute('INSERT INTO readings VALUES(?,1,3,11,0.4)',(stamp,))
        con.execute('INSERT INTO readings VALUES(?,1,3,8,0.8)',(stamp,))
        con.execute('INSERT INTO readings VALUES(?,1,3,23,-0.4)',(stamp,))
    for i,stamp in enumerate(range(int(first.timestamp())-3600,int(last.timestamp()),3600)):
        con.execute('INSERT INTO readings VALUES(?,1,3,10,?)',(stamp,100+i if not gas_reset or i<5 else i-5))
    con.execute('INSERT INTO readings VALUES(?,78,3,11,1)',(int(first.timestamp()),))
    con.commit(); con.close()
    return GridFlexLoader(path)


def test_import_export_and_counter_units_and_readonly(tmp_path):
    loader=database(tmp_path)
    assert loader.included_households == {'House1'}
    points=loader.load('House1')
    assert len(points)==2
    assert points[0].electricity_kwh == pytest.approx(9.6)
    assert points[0].electricity_export_kwh == pytest.approx(19.2)
    assert points[0].gas_m3 == pytest.approx(24)
    assert points[0].electricity_basis == 'grid_import'
    with loader.connect() as con:
        with pytest.raises(sqlite3.OperationalError): con.execute('DELETE FROM readings')
    with pytest.raises(ValueError): loader.load('House78')
    with pytest.raises(ValueError): loader.load('House1 OR 1=1')


def test_missing_intervals_and_gas_reset_are_not_filled(tmp_path):
    points=database(tmp_path,missing_e=True,gas_reset=True).load('House1')
    assert points[0].electricity_kwh is None
    assert points[0].n_elec_intervals==95
    assert points[0].gas_m3 is None
    assert points[0].n_gas_hours==23
    assert points[1].gas_m3 == 24


@pytest.mark.parametrize('start,hours',[('2019-03-31',23),('2019-10-27',25)])
def test_dst_daily_counts_follow_real_local_day(tmp_path,start,hours):
    point=database(tmp_path,start=start,days=1).load('House1')[0]
    assert point.n_gas_hours == point.expected_gas_hours == hours
    assert point.n_elec_intervals == point.expected_elec_intervals == hours*4
    assert valid(point,'electricity_kwh') and valid(point,'gas_m3')
    assert build_profile([point],'House1')['data_quality']==[]


def test_absent_database_has_no_catalog_households(tmp_path):
    loader=GridFlexLoader(tmp_path/'missing.db')
    assert loader.available is False
    assert loader.included_households == set()
