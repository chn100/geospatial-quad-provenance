from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from psycopg2.extras import execute_values, Json

from api.db import get_conn
from api.quadkeys import circle_to_quadkeys

app = FastAPI(title="ICU Near Boston Quad-Tree + Provenance MVP", version="0.1.0")

BOSTON = {"lon": -71.0589, "lat": 42.3601}
DEFAULT_RADIUS_METERS = 16093.4  # 10 miles

class CandidateRequest(BaseModel):
    lon: float = BOSTON["lon"]
    lat: float = BOSTON["lat"]
    radiusMeters: float = DEFAULT_RADIUS_METERS
    level: int = 12
    collectionId: str = "col_hospitals_ma"
    requiresICU: bool = True

class ExactSearchRequest(CandidateRequest):
    includeProvenance: bool = True
    queryText: str = "Find hospitals with ICU capacity within 10 miles of Boston"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/demo/query")
def demo_query():
    return {
        "query": "Find hospitals with ICU capacity within 10 miles of Boston",
        "center": BOSTON,
        "radiusMeters": DEFAULT_RADIUS_METERS,
        "radiusMiles": 10,
        "candidateStrategy": "quad-tree level 12 bbox candidate routing",
        "truthStrategy": "PostGIS ST_DWithin on geography",
    }

@app.post("/search/candidates")
def candidate_search(req: CandidateRequest):
    quadkeys = circle_to_quadkeys(req.lon, req.lat, req.radiusMeters, req.level)
    with get_conn() as conn, conn.cursor() as cur:
        where_icu = "AND (f.properties->>'hasICU')::boolean = true" if req.requiresICU else ""
        cur.execute(f"""
            SELECT DISTINCT f.id, f.name, f.properties, ST_X(f.geom) AS lon, ST_Y(f.geom) AS lat, s.quadkey
            FROM spatial_index_entries s
            JOIN features f ON f.id = s.feature_id
            WHERE s.level = %s
              AND s.quadkey = ANY(%s)
              AND f.collection_id = %s
              AND f.status = 'active'
              {where_icu}
            ORDER BY f.name
        """, (req.level, quadkeys, req.collectionId))
        rows = cur.fetchall()
    return {
        "quadkeyCount": len(quadkeys),
        "candidateCount": len(rows),
        "quadkeys": quadkeys,
        "candidates": rows,
        "note": "Candidates are not authoritative; run /search/exact for PostGIS validation."
    }

@app.post("/search/exact")
def exact_search(req: ExactSearchRequest):
    quadkeys = circle_to_quadkeys(req.lon, req.lat, req.radiusMeters, req.level)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO search_runs (query_text, center, radius_meters, property_filters, quad_levels)
            VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s)
            RETURNING id
        """, (req.queryText, req.lon, req.lat, req.radiusMeters, Json({"hasICU": req.requiresICU}), [req.level]))
        search_run_id = cur.fetchone()["id"]

        execute_values(cur, """
            INSERT INTO search_result_edges (search_run_id, role, entity_id)
            VALUES %s
            ON CONFLICT DO NOTHING
        """, [(search_run_id, "used_quadkey", q) for q in quadkeys])

        where_icu = "AND (f.properties->>'hasICU')::boolean = true" if req.requiresICU else ""
        cur.execute(f"""
            WITH candidates AS (
                SELECT DISTINCT f.*
                FROM spatial_index_entries s
                JOIN features f ON f.id = s.feature_id
                WHERE s.level = %s
                  AND s.quadkey = ANY(%s)
                  AND f.collection_id = %s
                  AND f.status = 'active'
                  {where_icu}
            ), exact AS (
                SELECT c.*,
                       ST_Distance(c.geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) AS distance_meters
                FROM candidates c
                WHERE ST_DWithin(c.geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
            )
            SELECT id, name, properties, ST_X(geom) AS lon, ST_Y(geom) AS lat, distance_meters
            FROM exact
            ORDER BY distance_meters ASC
        """, (req.level, quadkeys, req.collectionId, req.lon, req.lat, req.lon, req.lat, req.radiusMeters))
        exact_rows = cur.fetchall()

        cur.execute(f"""
            SELECT COUNT(DISTINCT f.id) AS n
            FROM spatial_index_entries s
            JOIN features f ON f.id = s.feature_id
            WHERE s.level = %s
              AND s.quadkey = ANY(%s)
              AND f.collection_id = %s
              AND f.status = 'active'
              {where_icu}
        """, (req.level, quadkeys, req.collectionId))
        candidate_count = cur.fetchone()["n"]
        validated_ids = {str(r["id"]) for r in exact_rows}

        cur.execute(f"""
            SELECT DISTINCT f.id
            FROM spatial_index_entries s
            JOIN features f ON f.id = s.feature_id
            WHERE s.level = %s
              AND s.quadkey = ANY(%s)
              AND f.collection_id = %s
              AND f.status = 'active'
              {where_icu}
        """, (req.level, quadkeys, req.collectionId))
        candidate_ids = {str(r["id"]) for r in cur.fetchall()}
        rejected_ids = candidate_ids - validated_ids

        edge_rows = []
        edge_rows.extend((search_run_id, "candidate", fid, None, Json({})) for fid in candidate_ids)
        edge_rows.extend((search_run_id, "validated", fid, None, Json({"predicate": "ST_DWithin"})) for fid in validated_ids)
        edge_rows.extend((search_run_id, "rejected", fid, "outside exact radius after PostGIS ST_DWithin", Json({})) for fid in rejected_ids)
        if edge_rows:
            execute_values(cur, """
                INSERT INTO search_result_edges (search_run_id, role, entity_id, reason, metadata)
                VALUES %s ON CONFLICT DO NOTHING
            """, edge_rows)

        cur.execute("""
            UPDATE search_runs
            SET candidate_count = %s, validated_count = %s, rejected_count = %s
            WHERE id = %s
        """, (candidate_count, len(validated_ids), len(rejected_ids), search_run_id))

        provenance_by_feature: Dict[str, List[Dict[str, Any]]] = {}
        if req.includeProvenance and validated_ids:
            cur.execute("""
                SELECT pe.id, pe.activity_type, pe.agent, pe.parameters, pe.quality_metrics,
                       peg.entity_id AS feature_id
                FROM provenance_edges peg
                JOIN provenance_events pe ON pe.id = peg.provenance_event_id
                WHERE peg.role = 'generated'
                  AND peg.entity_type = 'feature'
                  AND peg.entity_id = ANY(%s)
                ORDER BY pe.started_at DESC
            """, (list(validated_ids),))
            for p in cur.fetchall():
                provenance_by_feature.setdefault(p["feature_id"], []).append({
                    "provenanceEventId": p["id"],
                    "activityType": p["activity_type"],
                    "agent": p["agent"],
                    "parameters": p["parameters"],
                    "qualityMetrics": p["quality_metrics"],
                })

        results = []
        for r in exact_rows:
            fid = str(r["id"])
            results.append({
                "id": fid,
                "name": r["name"],
                "lon": float(r["lon"]),
                "lat": float(r["lat"]),
                "distanceMeters": float(r["distance_meters"]),
                "distanceMiles": float(r["distance_meters"]) / 1609.344,
                "properties": r["properties"],
                "provenance": provenance_by_feature.get(fid, []),
            })

        return {
            "searchRunId": search_run_id,
            "queryText": req.queryText,
            "quadkeyCount": len(quadkeys),
            "candidateCount": candidate_count,
            "validatedCount": len(results),
            "rejectedCandidateCount": len(rejected_ids),
            "results": results,
        }

@app.get("/search-runs/{search_run_id}/explain")
def explain_search(search_run_id: str):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, query_text, radius_meters, candidate_count, validated_count, rejected_count, created_at FROM search_runs WHERE id = %s", (search_run_id,))
        run = cur.fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="search run not found")
        cur.execute("""
            SELECT role, COUNT(*) AS n
            FROM search_result_edges
            WHERE search_run_id = %s
            GROUP BY role
            ORDER BY role
        """, (search_run_id,))
        counts = cur.fetchall()
        cur.execute("""
            SELECT role, entity_id, reason, metadata
            FROM search_result_edges
            WHERE search_run_id = %s
            ORDER BY role, entity_id
            LIMIT 200
        """, (search_run_id,))
        edges = cur.fetchall()
    return {"searchRun": run, "edgeCounts": counts, "sampleEdges": edges}

@app.get("/features/{feature_id}/provenance")
def feature_provenance(feature_id: str):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT pe.*, peg.role, peg.entity_type, peg.entity_id
            FROM provenance_edges peg
            JOIN provenance_events pe ON pe.id = peg.provenance_event_id
            WHERE peg.entity_id = %s
            ORDER BY pe.started_at DESC
        """, (feature_id,))
        rows = cur.fetchall()
    return {"featureId": feature_id, "provenanceEvents": rows}
