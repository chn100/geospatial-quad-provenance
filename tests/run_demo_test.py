import json
import time
import requests

BASE = "http://localhost:8000"


def post(path, body):
    r = requests.post(BASE + path, json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def get(path):
    r = requests.get(BASE + path, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    for _ in range(30):
        try:
            print(get("/health"))
            break
        except Exception:
            time.sleep(1)

    query = {
        "lon": -71.0589,
        "lat": 42.3601,
        "radiusMeters": 16093.4,
        "level": 12,
        "collectionId": "col_hospitals_ma",
        "requiresICU": True,
    }
    candidates = post("/search/candidates", query)
    exact = post("/search/exact", {**query, "includeProvenance": True})
    explanation = get(f"/search-runs/{exact['searchRunId']}/explain")

    print("\nCANDIDATE SEARCH")
    print(json.dumps({
        "quadkeyCount": candidates["quadkeyCount"],
        "candidateCount": candidates["candidateCount"],
        "sampleNames": [c["name"] for c in candidates["candidates"][:5]],
    }, indent=2, default=str))

    print("\nEXACT SEARCH")
    print(json.dumps({
        "searchRunId": exact["searchRunId"],
        "candidateCount": exact["candidateCount"],
        "validatedCount": exact["validatedCount"],
        "rejectedCandidateCount": exact["rejectedCandidateCount"],
        "topResults": [
            {
                "name": r["name"],
                "distanceMiles": round(r["distanceMiles"], 2),
                "hasProvenance": bool(r["provenance"]),
            }
            for r in exact["results"][:8]
        ],
    }, indent=2, default=str))

    print("\nSEARCH EXPLANATION")
    print(json.dumps(explanation["edgeCounts"], indent=2, default=str))

    assert exact["candidateCount"] >= exact["validatedCount"]
    assert exact["validatedCount"] > 0
    assert any(r["provenance"] for r in exact["results"])
    assert exact["rejectedCandidateCount"] >= 0
    print("\nPASS: quad-tree produced candidates, PostGIS validated exact truth, provenance is attached.")

if __name__ == "__main__":
    main()
