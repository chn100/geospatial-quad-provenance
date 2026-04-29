import os
import random
import uuid
from datetime import datetime, timezone
from psycopg2.extras import execute_values, Json

from api.db import get_conn
from api.quadkeys import lonlat_to_quadkey, quadkey_bbox_wkt

random.seed(42)
COLLECTION_ID = "col_hospitals_ma"
LEVELS = [8, 12, 16]

ANCHOR_HOSPITALS = [
    ("Mass General Hospital", -71.0688, 42.3632, True, "level_i_trauma"),
    ("Brigham and Women's Hospital", -71.1065, 42.3358, True, "teaching"),
    ("Beth Israel Deaconess Medical Center", -71.1054, 42.3389, True, "teaching"),
    ("Boston Medical Center", -71.0726, 42.3342, True, "safety_net"),
    ("Tufts Medical Center", -71.0645, 42.3496, True, "teaching"),
    ("Cambridge Health Alliance", -71.1056, 42.3751, True, "community"),
    ("Newton-Wellesley Hospital", -71.2466, 42.3318, True, "community"),
    ("South Shore Hospital", -70.9564, 42.1751, True, "regional"),
    ("Winchester Hospital", -71.1545, 42.4668, True, "community"),
    ("Minute Clinic Downtown Boston", -71.0580, 42.3605, False, "clinic"),
]


def synthetic_hospitals(n=750):
    # Roughly Massachusetts / nearby southern New England extent.
    for i in range(n):
        lon = random.uniform(-73.5, -69.8)
        lat = random.uniform(41.2, 42.95)
        # bias some around Boston metro so the query has candidates and rejects.
        if i < 250:
            lon = random.gauss(-71.0589, 0.22)
            lat = random.gauss(42.3601, 0.16)
        has_icu = random.random() < (0.42 if i < 250 else 0.22)
        kind = random.choice(["community", "regional", "critical_access", "clinic"])
        yield (f"Synthetic Facility {i:04d}", lon, lat, has_icu, kind)


def main():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE search_result_edges, search_runs, provenance_edges, provenance_events, spatial_index_entries, features, assets, collections RESTART IDENTITY CASCADE")
        cur.execute("""
            INSERT INTO collections (id, name, description)
            VALUES (%s, %s, %s)
        """, (COLLECTION_ID, "Massachusetts Hospital Demonstration Dataset", "Synthetic hospital point data for ICU near Boston quad-tree/PostGIS MVP"))

        cur.execute("""
            INSERT INTO assets (collection_id, uri, format, checksum, metadata)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (COLLECTION_ID, "memory://synthetic-hospitals-ma", "synthetic", "sha256:demo", Json({"seed": 42, "note": "not real hospital capacity data"})))
        asset_id = cur.fetchone()["id"]

        cur.execute("""
            INSERT INTO provenance_events (activity_type, ended_at, agent, parameters, quality_metrics)
            VALUES (%s, now(), %s, %s, %s)
            RETURNING id
        """, (
            "seed_synthetic_hospital_dataset",
            Json({"type": "software", "name": "scripts/seed_demo.py", "version": "0.1.0"}),
            Json({"randomSeed": 42, "levels": LEVELS}),
            Json({"synthetic": True})
        ))
        prov_id = cur.fetchone()["id"]
        cur.execute("""
            INSERT INTO provenance_edges (provenance_event_id, role, entity_type, entity_id)
            VALUES (%s, 'used', 'asset', %s)
        """, (prov_id, str(asset_id)))

        rows = list(ANCHOR_HOSPITALS) + list(synthetic_hospitals())
        feature_rows = []
        for name, lon, lat, has_icu, kind in rows:
            feature_rows.append((COLLECTION_ID, "hospital", name, Json({"hasICU": has_icu, "facilityClass": kind}), lon, lat, asset_id))

        inserted = execute_values(cur, """
            INSERT INTO features (collection_id, feature_type, name, properties, geom, source_asset_id)
            VALUES %s
            RETURNING id, name, ST_X(geom) AS lon, ST_Y(geom) AS lat
        """, feature_rows, template="(%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)", fetch=True)

        prov_edges = [(prov_id, "generated", "feature", str(r["id"])) for r in inserted]
        execute_values(cur, """
            INSERT INTO provenance_edges (provenance_event_id, role, entity_type, entity_id)
            VALUES %s
        """, prov_edges)

        index_rows = []
        seen_cells = {}
        for r in inserted:
            lon, lat = float(r["lon"]), float(r["lat"])
            for level in LEVELS:
                qk = lonlat_to_quadkey(lon, lat, level)
                if qk not in seen_cells:
                    seen_cells[qk] = quadkey_bbox_wkt(qk)
                index_rows.append((r["id"], qk, level, "centroid", True, seen_cells[qk]))

        execute_values(cur, """
            INSERT INTO spatial_index_entries (feature_id, quadkey, level, coverage_type, is_primary, cell_bbox)
            VALUES %s
        """, index_rows, template="(%s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326))")

        print(f"Seeded {len(inserted)} hospital features")
        print(f"Asset: {asset_id}")
        print(f"Provenance event: {prov_id}")
        print("Demo query: hospitals with ICU within 10 miles of Boston")

if __name__ == "__main__":
    main()
