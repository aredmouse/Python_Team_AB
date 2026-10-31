# pytest가 테스트 전에 읽는 파일. 테스트들이 함께 쓰는 가짜 데이터를 만든다.
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from src.data_loader import DataLoader


class SmallLoader(DataLoader):
    DISTRICT_COUNT = 2      # 가짜 데이터에는 자치구가 2개뿐


BUS_HEADER = ['노드 ID', '정류소번호', '정류소명', 'X좌표', 'Y좌표', '정류소 타입']
BUS_ROWS = [
    ('00001', '1', '종로A', 126.91, 37.52, '일반차로'),
    ('00002', '2', '종로B', 126.92, 37.53, '중앙차로'),
    ('00003', '3', '중구A', 126.97, 37.52, '마을버스'),
    ('00004', '4', '서울밖', 127.20, 37.52, '일반차로'),
    ('00005', '5', '선착장', 126.93, 37.52, '한강선착장'),
    ('00006', '6', '좌표없음', None, 37.52, '일반차로'),
    ('00001', '1', '종로A', 126.91, 37.52, '일반차로'),     # 완전히 같은 중복
]

POPULATION_HEADER = ['기준일ID', '시구코드', '시구명', '총생활인구수']
POPULATION_ROWS = [
    ('20261004', '11000', '서울시', 500.0),
    ('20261004', '11110', '종로구', 200.0),
    ('20261004', '11140', '중구', 300.0),
    ('20261003', '11110', '종로구', 199.0),
    ('20261003', '11140', '중구', 299.0),
]

DISTRICTS = [
    ('11110', '종로구', box(126.90, 37.50, 126.95, 37.55)),
    ('11140', '중구', box(126.95, 37.50, 127.00, 37.55)),
]


def write_raw(raw_dir, bus_rows, population_rows, districts, encoding):
    (raw_dir / 'districts').mkdir(parents=True)
    bus = pd.DataFrame(bus_rows, columns=BUS_HEADER)
    bus.to_csv(raw_dir / DataLoader.BUS_FILE, index=False, encoding=encoding)
    population = pd.DataFrame(population_rows, columns=POPULATION_HEADER)
    population.to_csv(raw_dir / DataLoader.POPULATION_FILE, index=False,
                      encoding=encoding)

    codes, names, shapes = zip(*districts)
    boundary = gpd.GeoDataFrame({'SIGNGU_CD': codes, 'SIGNGU_NM': names},
                                geometry=list(shapes), crs='EPSG:4326')
    boundary.to_crs('EPSG:5181').to_file(raw_dir / DataLoader.DISTRICT_FILE)


@pytest.fixture
def make_loader(tmp_path):
    def make(target_date='20261004', bus_rows=BUS_ROWS,
             population_rows=POPULATION_ROWS, districts=DISTRICTS,
             encoding='cp949'):
        raw_dir = tmp_path / 'raw'
        write_raw(raw_dir, bus_rows, population_rows, districts, encoding)
        return SmallLoader(raw_dir, target_date)
    return make


@pytest.fixture
def loader(make_loader):
    return make_loader()
