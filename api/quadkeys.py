import math
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

MAX_LAT = 85.05112878

@dataclass(frozen=True)
class Tile:
    x: int
    y: int
    z: int


def clip(value: float, min_value: float, max_value: float) -> float:
    return min(max(value, min_value), max_value)


def lonlat_to_tile(lon: float, lat: float, z: int) -> Tile:
    lat = clip(lat, -MAX_LAT, MAX_LAT)
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return Tile(clip(x, 0, n - 1), clip(y, 0, n - 1), z)


def tile_to_quadkey(tile: Tile) -> str:
    quadkey = []
    for i in range(tile.z, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if tile.x & mask:
            digit += 1
        if tile.y & mask:
            digit += 2
        quadkey.append(str(digit))
    return ''.join(quadkey)


def quadkey_to_tile(quadkey: str) -> Tile:
    x = y = 0
    z = len(quadkey)
    for i, c in enumerate(quadkey):
        mask = 1 << (z - i - 1)
        d = int(c)
        if d & 1:
            x |= mask
        if d & 2:
            y |= mask
    return Tile(x, y, z)


def tile_bounds(tile: Tile) -> Tuple[float, float, float, float]:
    n = 2 ** tile.z
    lon_min = tile.x / n * 360.0 - 180.0
    lon_max = (tile.x + 1) / n * 360.0 - 180.0

    def y_to_lat(y: int) -> float:
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
        return math.degrees(lat_rad)

    lat_max = y_to_lat(tile.y)
    lat_min = y_to_lat(tile.y + 1)
    return lon_min, lat_min, lon_max, lat_max


def lonlat_to_quadkey(lon: float, lat: float, z: int) -> str:
    return tile_to_quadkey(lonlat_to_tile(lon, lat, z))


def bbox_to_quadkeys(bbox: Sequence[float], z: int, max_tiles: int = 20000) -> List[str]:
    min_lon, min_lat, max_lon, max_lat = bbox
    t1 = lonlat_to_tile(min_lon, max_lat, z)
    t2 = lonlat_to_tile(max_lon, min_lat, z)
    x_min, x_max = sorted((t1.x, t2.x))
    y_min, y_max = sorted((t1.y, t2.y))
    count = (x_max - x_min + 1) * (y_max - y_min + 1)
    if count > max_tiles:
        raise ValueError(f"bbox covers {count} tiles at level {z}; lower the level or raise max_tiles")
    return [tile_to_quadkey(Tile(x, y, z)) for x in range(x_min, x_max + 1) for y in range(y_min, y_max + 1)]


def bbox_around_point(lon: float, lat: float, radius_meters: float) -> Tuple[float, float, float, float]:
    # Good enough for candidate routing; exact search is delegated to PostGIS geography.
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = meters_per_deg_lat * math.cos(math.radians(lat))
    delta_lat = radius_meters / meters_per_deg_lat
    delta_lon = radius_meters / max(meters_per_deg_lon, 1.0)
    return (lon - delta_lon, lat - delta_lat, lon + delta_lon, lat + delta_lat)


def circle_to_quadkeys(lon: float, lat: float, radius_meters: float, z: int) -> List[str]:
    return bbox_to_quadkeys(bbox_around_point(lon, lat, radius_meters), z)


def quadkey_bbox_wkt(quadkey: str) -> str:
    xmin, ymin, xmax, ymax = tile_bounds(quadkey_to_tile(quadkey))
    return f"POLYGON(({xmin} {ymin}, {xmax} {ymin}, {xmax} {ymax}, {xmin} {ymax}, {xmin} {ymin}))"
