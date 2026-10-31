# [B] clean_bus_stops(), clean_population(), clean_districts(),
#     assign_districts(), summarize_districts()  [공동] run(), main.py
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from conftest import BUS_ROWS, DISTRICTS, POPULATION_ROWS
from main import ResultSaver
from src.data_loader import DataLoader

RAW_DIR = Path(__file__).resolve().parents[1] / 'data' / 'raw'


def clean_all(loader):
    loader.clean_bus_stops()
    loader.clean_population()
    loader.clean_districts()


@pytest.fixture
def cleaned(loader):
    loader.load_data()
    clean_all(loader)
    return loader


@pytest.fixture
def assigned(cleaned):
    cleaned.assign_districts()
    return cleaned


# 순서 지키기

@pytest.mark.parametrize('step', ['clean_bus_stops', 'clean_population',
                                  'clean_districts', 'assign_districts'])
def test_steps_need_load_first(loader, step):
    with pytest.raises(RuntimeError):
        getattr(loader, step)()


@pytest.mark.parametrize('step', ['clean_bus_stops', 'clean_population',
                                  'clean_districts'])
def test_clean_twice_raises(cleaned, step):
    with pytest.raises(RuntimeError, match='이미'):
        getattr(cleaned, step)()


def test_assign_needs_clean_first(loader):
    loader.load_data()
    with pytest.raises(RuntimeError):
        loader.assign_districts()


def test_summarize_needs_assign_first(cleaned):
    with pytest.raises(RuntimeError):
        cleaned.summarize_districts()


def test_assign_and_summarize_twice_raise(assigned):
    with pytest.raises(RuntimeError, match='이미'):
        assigned.assign_districts()
    assigned.summarize_districts()
    with pytest.raises(RuntimeError, match='이미'):
        assigned.summarize_districts()


# 정제

def test_clean_bus_stops(cleaned):
    stops = cleaned.bus_stop_data
    assert list(stops.columns) == ['stop_id', 'stop_name', 'longitude', 'latitude']
    assert stops['stop_id'].tolist() == ['00001', '00002', '00003', '00004']
    assert cleaned.validation_report['bus_stops'] == {
        'excluded_stop_types': 1, 'invalid_rows': 1, 'duplicate_rows': 1,
        'conflicting_stop_ids': [], 'rows': 4}


def test_blank_id_and_name_are_invalid(make_loader):
    rows = BUS_ROWS + [('  ', '7', '빈ID', 126.91, 37.52, '일반차로'),
                       ('00008', '8', None, 126.91, 37.52, '일반차로')]
    loader = make_loader(bus_rows=rows)
    loader.load_data()
    loader.clean_bus_stops()
    assert loader.validation_report['bus_stops']['invalid_rows'] == 3
    assert '00008' not in loader.bus_stop_data['stop_id'].tolist()


def test_conflicting_stop_id_is_recorded_and_dropped(make_loader):
    rows = BUS_ROWS + [('00001', '1', '다른이름', 126.91, 37.52, '일반차로')]
    loader = make_loader(bus_rows=rows)
    loader.load_data()
    loader.clean_bus_stops()
    assert loader.validation_report['bus_stops']['conflicting_stop_ids'] == ['00001']
    assert '00001' not in loader.bus_stop_data['stop_id'].tolist()


def test_clean_population_picks_one_day(cleaned):
    people = cleaned.population_data
    assert list(people.columns) == ['date', 'district_code', 'district_name',
                                    'living_population']
    assert people['district_code'].tolist() == ['11110', '11140']    # 11000 제외
    assert people['living_population'].tolist() == [200.0, 300.0]


def test_missing_date_raises(make_loader):
    loader = make_loader(target_date='20240229')
    loader.load_data()
    with pytest.raises(ValueError, match='20240229'):
        loader.clean_population()


def test_zero_population_raises(make_loader):
    rows = POPULATION_ROWS[:2] + [('20261004', '11140', '중구', 0.0)]
    loader = make_loader(population_rows=rows)
    loader.load_data()
    with pytest.raises(ValueError, match='11140'):
        loader.clean_population()


def test_clean_districts(cleaned):
    districts = cleaned.district_data
    assert list(districts.columns) == ['district_code', 'district_name', 'geometry']
    assert districts.crs.to_epsg() == 5181


def test_float_district_code_is_fixed(loader):
    loader.load_data()
    loader.district_data['SIGNGU_CD'] = loader.district_data['SIGNGU_CD'].astype(float)
    loader.clean_districts()
    assert loader.district_data['district_code'].tolist() == ['11110', '11140']


def test_blank_district_code_raises(loader):
    loader.load_data()
    loader.district_data.loc[0, 'SIGNGU_CD'] = None
    with pytest.raises(ValueError, match='숫자가 아닌 코드'):
        loader.clean_districts()


def test_wrong_district_count_raises(loader):
    real = DataLoader(loader.bus_file.parent, '20261004')      # 25개를 기대
    real.load_data()
    with pytest.raises(ValueError):
        real.clean_districts()


# 병합

def test_assign_districts(assigned):
    stops = assigned.bus_stop_data
    assert list(stops.columns) == ['stop_id', 'stop_name', 'longitude', 'latitude',
                                   'district_code', 'district_name']
    assert stops['district_code'].tolist() == ['11110', '11110', '11140']


def test_assign_records_stops_outside_seoul(assigned):
    info = assigned.validation_report['merge']
    assert info['unassigned_stops'] == 1
    assert info['unassigned_stop_ids'] == ['00004']
    assert info['multiple_assigned_stops'] == 0


def test_summarize_builds_district_summary(assigned):
    assigned.summarize_districts()
    districts = assigned.district_data
    assert list(districts.columns) == ['district_code', 'district_name', 'geometry',
                                       'area_km2', 'living_population',
                                       'population_date', 'bus_stop_count']
    assert districts['bus_stop_count'].tolist() == [2, 1]
    assert districts['living_population'].tolist() == [200.0, 300.0]
    assert (districts['area_km2'] > 0).all()
    assert districts.crs.to_epsg() == 4326


def test_code_mismatch_raises(make_loader):
    districts = [DISTRICTS[0], ('99999', '없는구', DISTRICTS[1][2])]
    loader = make_loader(districts=districts)
    loader.load_data()
    clean_all(loader)
    loader.assign_districts()
    with pytest.raises(ValueError, match='99999'):
        loader.summarize_districts()


def test_empty_shape_fails_final_check(cleaned):
    from shapely.geometry import Polygon
    cleaned.district_data.loc[0, 'geometry'] = Polygon()
    cleaned.assign_districts()
    with pytest.raises(ValueError, match='면적'):
        cleaned.summarize_districts()


def test_district_without_stops_counts_zero(make_loader):
    rows = [row for row in BUS_ROWS if row[2] != '중구A']
    _, districts, _ = make_loader(bus_rows=rows).run()
    assert districts['bus_stop_count'].tolist() == [2, 0]


# 실행

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
    stops, districts, report = DataLoader(RAW_DIR, '20261004').run()
    assert len(districts) == 25
    assert len(stops) == 11215                  # 11,236 - 선착장 8 - 서울 밖 13
    assert report['merge']['unassigned_stops'] == 13
    assert districts['bus_stop_count'].sum() == len(stops)
