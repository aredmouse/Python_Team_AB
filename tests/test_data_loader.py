# [A] __init__(), from_folder(), __str__(), load_data()
from pathlib import Path

import pytest

from conftest import SmallLoader
from src.data_loader import DataLoader

RAW_DIR = Path(__file__).resolve().parents[1] / 'data' / 'raw'


def test_init_starts_empty(tmp_path):
    loader = DataLoader(tmp_path / 'a.csv', tmp_path / 'b.csv',
                        tmp_path / 'c.shp', '20261004')
    assert loader.bus_file == tmp_path / 'a.csv'
    assert loader.bus_stop_data is None
    assert loader.population_data is None
    assert loader.district_data is None
    assert loader.validation_report == {}


@pytest.mark.parametrize('given', ['20261004', '2026-10-04', 20261004])
def test_init_normalizes_date(given):
    assert DataLoader('a', 'b', 'c', given).target_date == '20261004'


def test_from_folder_builds_paths(tmp_path):
    loader = DataLoader.from_folder(tmp_path, '20261004')
    assert loader.bus_file == tmp_path / '서울시 버스정류소 위치정보.csv'
    assert loader.district_file == tmp_path / 'districts' / 'districts.shp'


def test_from_folder_keeps_subclass(tmp_path):
    assert type(SmallLoader.from_folder(tmp_path, '20261004')) is SmallLoader


def test_str_before_and_after_run(loader):
    assert str(loader) == 'DataLoader(20261004, 아직 실행 전)'
    loader.run()
    assert str(loader) == 'DataLoader(20261004, 정류장 3개, 자치구 2개)'


def test_load_reads_three_tables(loader):
    assert loader.load_data() is None          # 반환하지 않고 self에 저장
    assert len(loader.bus_stop_data) == 7
    assert len(loader.population_data) == 5
    assert len(loader.district_data) == 2


def test_load_keeps_original_columns(loader):
    loader.load_data()
    assert list(loader.bus_stop_data.columns)[:3] == ['노드 ID', '정류소번호', '정류소명']
    assert '시구코드' in loader.population_data.columns
    assert 'SIGNGU_CD' in loader.district_data.columns


def test_load_keeps_leading_zeros(loader):
    loader.load_data()
    assert loader.bus_stop_data['노드 ID'][0] == '00001'
    assert loader.population_data['시구코드'][0] == '11000'   # 합계 행도 그대로


def test_load_keeps_crs_and_records_rows(loader):
    loader.load_data()
    assert loader.district_data.crs.to_epsg() == 5181
    assert loader.validation_report['raw_rows'] == {
        'bus_stops': 7, 'population': 5, 'districts': 2}


def test_load_reads_utf8(make_loader):
    loader = make_loader(encoding='utf-8-sig')
    loader.load_data()
    assert loader.bus_stop_data['정류소명'][0] == '종로A'


def test_missing_csv_raises(loader):
    loader.bus_file = loader.bus_file.with_name('없는파일.csv')
    with pytest.raises(FileNotFoundError, match='없는파일.csv'):
        loader.load_data()


def test_missing_shp_companion_raises(loader):
    loader.district_file.with_suffix('.dbf').unlink()
    with pytest.raises(FileNotFoundError, match='.dbf'):
        loader.load_data()


def test_unreadable_encoding_raises(loader):
    loader.bus_file.write_bytes(b'\xff\xfe\x00\xd8 broken \x81\x00')
    with pytest.raises(ValueError, match='인코딩'):
        loader.load_data()


@pytest.mark.skipif(not (RAW_DIR / DataLoader.BUS_FILE).exists(),
                    reason='data/raw에 실제 원본이 없음')
def test_load_real_files():
    loader = DataLoader.from_folder(RAW_DIR, '20261004')
    loader.load_data()
    assert loader.validation_report['raw_rows'] == {
        'bus_stops': 11236, 'population': 35672, 'districts': 25}
    assert loader.validation_report['district_crs'] == 'EPSG:5181'
