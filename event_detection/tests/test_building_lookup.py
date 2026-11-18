from datetime import datetime
import pytest
from fastapi.testclient import TestClient
import event_detection.building_lookup as lookup
import event_detection.api.app as api

BAG_ID='0917010000051699'
PAND=lookup.BAG+'/pand/items/624b1f8a-dda3-58ec-a2e4-d1934728a768'


def test_postcode_lookup_returns_choices_and_never_picks_first(monkeypatch):
    def fake(url,params=None,headers=None):
        assert params['fq']==['type:adres','postcode:6411CR']
        return {'response':{'numFound':2,'docs':[
            {'postcode':'6411CR','adresseerbaarobject_id':BAG_ID,'weergavenaam':'Example 2','huisnummer':2},
            {'postcode':'6411CR','adresseerbaarobject_id':'0917010000022693','weergavenaam':'Example 3','huisnummer':3}]}}
    monkeypatch.setattr(lookup,'fetch_json',fake)
    result=lookup.search_addresses('6411 cr')
    assert len(result['addresses'])==2
    assert 'selected' not in result
    for invalid in ('<script>', '6411CR OR *:*','0000AA'):
        with pytest.raises(ValueError): lookup.search_addresses(invalid)


def test_bag_enrichment_and_no_key_keeps_label_unknown(monkeypatch):
    monkeypatch.delenv('EP_ONLINE_API_KEY',raising=False)
    def fake(url,params=None,headers=None):
        if '/verblijfsobject/' in url:
            return {'features':[{'properties':{'identificatie':BAG_ID,'oppervlakte':70,'gebruiksdoel':'woonfunctie','pand.href':[PAND,'https://attacker.invalid/secret']}}]}
        assert url==PAND
        return {'properties':{'bouwjaar':1970}}
    monkeypatch.setattr(lookup,'fetch_json',fake)
    result=lookup.lookup_building(BAG_ID)
    assert result['floor_area_m2']==70 and result['building_year']==1970
    assert result['energy_label'] is None
    assert result['energy_performance']['status']=='api_key_required'


def test_ep_online_uses_current_matching_record_and_distinguishes_units(monkeypatch):
    monkeypatch.setenv('EP_ONLINE_API_KEY','test-key')
    def fake(url,params=None,headers=None):
        assert headers['Authorization']=='test-key'
        return [{'BAGVerblijfsobjectID':BAG_ID,'Geldig_tot':'2099-01-01','Registratiedatum':'2025-01-01','Energieklasse':'C','Energiebehoefte':65,'Warmtebehoefte':50,'Compactheid':1.2,'BerekendeEnergieverbruik':100},
                {'BAGVerblijfsobjectID':BAG_ID,'Geldig_tot':'2000-01-01','Registratiedatum':'2026-01-01','Energieklasse':'A'}]
    monkeypatch.setattr(lookup,'fetch_json',fake)
    result=lookup.energy_context(BAG_ID)
    assert result['energy_label']=='C'
    assert result['energy_demand_kwh_m2_year']==65
    assert result['calculated_energy_kwh_m2_year']==100
    assert result['thermal_zone_area_m2'] is None


def test_api_requires_explicit_confirmation_before_applying_building(monkeypatch):
    client=TestClient(api.app)
    request={'dataset':'zonnedael','household':'Klant 34','building_bag_id':BAG_ID}
    assert client.post('/product/analyze',json=request).status_code==422
    monkeypatch.setattr(api,'lookup_building',lambda bag_id: {'bag_id':bag_id,'floor_area_m2':70,'energy_label':'C','building_year':1970})
    response=client.post('/product/analyze',json={**request,'building_confirmed':True,'home':{'floor_area_m2':85}})
    assert response.status_code==200
    home=response.json()['profile']['home']
    assert home['floor_area_m2']==85  # Explicit user input takes priority.
    assert home['energy_label']=='C'
    assert home['building_context']['bag_id']==BAG_ID


def test_lookup_failure_is_actionable_and_does_not_crash_profile(monkeypatch):
    client=TestClient(api.app)
    def unavailable(*args,**kwargs): raise lookup.LookupUnavailable('Service unavailable')
    monkeypatch.setattr(api,'search_addresses',unavailable)
    assert client.post('/homes/search',json={'postcode':'6411CR'}).status_code==502
    assert client.post('/homes/lookup',json={'bag_id':'http://evil'}).status_code==422
    response=client.post('/profiles/build',json={'dataset':'zonnedael','household':'Klant 34'})
    assert response.status_code==200
