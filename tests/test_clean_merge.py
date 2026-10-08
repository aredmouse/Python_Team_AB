# [B] clean_data(), merge_data()  [공동] run(), main.py
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from conftest import BUS_ROWS, DISTRICTS, POPULATION_ROWS
from main import ResultSaver
from src.data_loader import DataLoader

RAW_DIR = Path(__file__).resolve().parents[1] / 'data' / 'raw'


@pytest.fixture
def cleaned(loader):
    loader.load_data()
    loader.clean_data()
    return loader


def test_clean_needs_load_first(loader):
    with pytest.raises(RuntimeError):
        loader.clean_data()


def test_clean_bus_stops(cleaned):
    stops = cleaned.bus_stop_data
    assert list(stops.columns) == ['stop_id', 'stop_name', 'longitude', 'latitude']
    assert stops['stop_id'].tolist() == ['00001', '00002', '00003', '00004']
    assert cleaned.validation_report['bus_stops'] == {
        'excluded_stop_types': 1, 'invalid_rows': 1, 'duplicate_rows': 1, 'rows': 4}


def test_clean_population_picks_one_day(cleaned):
    people = cleaned.population_data
    assert list(people.columns) == ['date', 'district_code', 'district_name',
                                    'living_population']
    assert people['district_code'].tolist() == ['11110', '11140']    # 11000 제외
    assert people['living_population'].tolist() == [200.0, 300.0]


def test_clean_districts(cleaned):
    districts = cleaned.district_data
    assert list(districts.columns) == ['district_code', 'district_name', 'geometry']
    assert districts.crs.to_epsg() == 5181


def test_missing_date_raises(make_loader):
    loader = make_loader(target_date='20240229')
    loader.load_data()
    with pytest.raises(ValueError, match='20240229'):
        loader.clean_data()


def test_conflicting_stop_id_raises(make_loader):
    rows = BUS_ROWS + [('00001', '1', '다른이름', 126.91, 37.52, '일반차로')]
    loader = make_loader(bus_rows=rows)
    loader.load_data()
    with pytest.raises(ValueError, match='00001'):
        loader.clean_data()


def test_zero_population_raises(make_loader):
    rows = POPULATION_ROWS[:2] + [('20261004', '11140', '중구', 0.0)]
    loader = make_loader(population_rows=rows)
    loader.load_data()
    with pytest.raises(ValueError, match='11140'):
        loader.clean_data()


def test_code_mismatch_raises(make_loader):
    districts = [DISTRICTS[0], ('99999', '없는구', DISTRICTS[1][2])]
    loader = make_loader(districts=districts)
    loader.load_data()
    with pytest.raises(ValueError, match='99999'):
        loader.clean_data()


def test_wrong_district_count_raises(loader):
    real = DataLoader(loader.bus_file, loader.population_file,
                      loader.district_file, '20261004')      # 25개를 기대
    real.load_data()
    with pytest.raises(ValueError):
        real.clean_data()


def test_merge_needs_clean_first(loader):
    loader.load_data()
    with pytest.raises(RuntimeError):
        loader.merge_data()


def test_merge_assigns_districts(cleaned):
    cleaned.merge_data()
    stops = cleaned.bus_stop_data
    assert list(stops.columns) == ['stop_id', 'stop_name', 'longitude', 'latitude',
                                   'district_code', 'district_name']
    assert stops['district_code'].tolist() == ['11110', '11110', '11140']


def test_merge_records_stops_outside_seoul(cleaned):
    cleaned.merge_data()
    info = cleaned.validation_report['merge']
    assert info['unassigned_stops'] == 1
    assert info['unassigned_stop_ids'] == ['00004']
    assert info['multiple_assigned_stops'] == 0


def test_merge_builds_district_summary(cleaned):
    cleaned.merge_data()
    districts = cleaned.district_data
    assert list(districts.columns) == ['district_code', 'district_name', 'geometry',
                                       'area_km2', 'living_population',
                                       'bus_stop_count']
    assert districts['bus_stop_count'].tolist() == [2, 1]
    assert districts['living_population'].tolist() == [200.0, 300.0]
    assert (districts['area_km2'] > 0).all()
    assert districts.crs.to_epsg() == 4326


def test_district_without_stops_counts_zero(make_loader):
    rows = [row for row in BUS_ROWS if row[2] != '중구A']
    _, districts, _ = make_loader(bus_rows=rows).run()
    assert districts['bus_stop_count'].tolist() == [2, 0]


def test_run_returns_three_results(loader):
    stops, districts, report = loader.run()
    assert stops is loader.bus_stop_data
    assert districts is loader.district_data
    assert set(report) == {'raw_rows', 'district_crs', 'bus_stops',
                           'population', 'districts', 'merge'}


def test_result_saver_writes_three_files(loader, tmp_path):
    stops, districts, report = loader.run()
    out_dir = tmp_path / 'processed'
    ResultSaver(out_dir).save(stops, districts, report)

    saved = pd.read_csv(out_dir / 'bus_stops.csv', dtype={'stop_id': str})
    assert saved['stop_id'].tolist() == ['00001', '00002', '00003']
    assert len(gpd.read_file(out_dir / 'districts.geojson')) == 2
    with open(out_dir / 'validation_report.json', encoding='utf-8') as f:
        assert json.load(f)['merge']['unassigned_stops'] == 1


@pytest.mark.skipif(not (RAW_DIR / DataLoader.BUS_FILE).exists(),
                    reason='data/raw에 실제 원본이 없음')
def test_run_real_files():
    stops, districts, report = DataLoader.from_folder(RAW_DIR, '20261004').run()
    assert len(districts) == 25
    assert len(stops) == 11215                  # 11,236 - 선착장 8 - 서울 밖 13
    assert report['merge']['unassigned_stops'] == 13
    assert districts['bus_stop_count'].sum() == len(stops)
