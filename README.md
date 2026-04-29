**Resource-Oriented Geospatial Model (Quad-Tree + PostGIS + Provenance)**

** **

**Quick Start**

docker compose up -d

docker compose exec api python scripts/seed_demo.py

docker compose exec api python tests/run_demo_test.py

 

**Overview**

This repository contains the reproducibility package for the paper:

**“A Resource-Oriented Geospatial Data Model with Quad-Tree Indexing and Provenance: Toward Scalable and Reproducible GeoAI Systems.”**

The project demonstrates how a geospatial system can separate:



* **Candidate selection** (quad-tree indexing)
* **Exact spatial validation** (PostGIS)
* **Provenance tracking** (explicit lineage graph)

into independent, interoperable components.

The goal is to test a central architectural question:

Can quad-tree candidate routing reduce the search space while PostGIS validates spatial truth and provenance remains attached to the result?


---

**Demonstration Scenario**

The system implements a reproducible geospatial query:

**Find ICU-capable healthcare facilities within 10 miles of Boston**

This query is evaluated using:



1. Quad-tree candidate filtering
2. Exact spatial validation using PostGIS
3. Provenance attachment for returned results


---

**What This Repository Demonstrates**

This prototype provides a minimal but complete implementation of the paper’s architecture:



* Explicit quad-tree spatial indexing
* Two-stage query execution (filter → validate)
* PostGIS-based geometric truth validation
* Provenance tracking of data generation and ingestion
* Synthetic dataset generation for reproducibility

This is not intended to be a production GIS system. \
It is a **reference implementation** for evaluating the architectural model.


---

**Repository Structure**

geospatial-quad-provenance/ \
├── api/              	# FastAPI application \
│   └── app.py \
├── scripts/          	# Data generation and loading \
│   └── seed_demo.py \
├── sql/              	# Database schema \
│   └── 01_schema.sql \
├── tests/            	# Reproducibility test \
│   └── run_demo_test.py \
├── docker-compose.yml	# PostGIS + API stack \
├── requirements.txt \
├── README.md \
└── LICENSE


---

**System Architecture**

The system follows a **two-stage spatial query model**:



1. **Quad-tree layer**
    * Routes query to relevant spatial cells
    * Reduces candidate feature set
2. **PostGIS layer**
    * Executes exact spatial predicates
    * Ensures geometric correctness
3. **Provenance layer**
    * Links results to source data and transformations
    * Enables reproducibility and traceability


---

**Setup Instructions**

**1. Start the system**

docker compose up -d

This starts:



* PostgreSQL with PostGIS
* API service


---

**2. Load synthetic dataset**

docker compose exec api python scripts/seed_demo.py

This will:



* Generate ~5,000 synthetic healthcare facility points
* Assign ICU capability attributes
* Build quad-tree index entries
* Create provenance records


---

**3. Run the demonstration test**

docker compose exec api python tests/run_demo_test.py


---

**Expected Output**

A successful run should produce output similar to:

Total features: 5000 \
Quad-tree candidates: 420 \
Exact spatial results: 100 \
Candidate reduction: ~91% \
Provenance attached: yes

Actual numbers may vary depending on random seed and configuration.


---

**Experimental Design**

The prototype evaluates three query strategies:



* Full scan (no index)
* R-tree only (PostGIS GiST index)
* Quad-tree + PostGIS (hybrid approach)

The key metric is **candidate reduction**, which determines how many spatial predicate evaluations are required.


---

**Reproducibility Notes**



* Synthetic dataset generation should use a fixed random seed for consistent results
* Timing results may vary depending on hardware and container configuration
* Candidate reduction and final result agreement are the primary evaluation metrics


---

**Relationship to the Paper**

This repository directly supports the experimental evaluation described in the manuscript.

It demonstrates:



* explicit representation of spatial index structures
* separation of candidate selection and validation
* integration of provenance into query results
* reproducible spatial query execution

The implementation makes the proposed architecture concrete and testable.


---

**Limitations**

This prototype currently focuses on:



* point-based proximity queries
* synthetic datasets

It does not yet include:



* polygon or network-based spatial queries
* spatiotemporal data
* adaptive quad-tree resolution
* production-scale ingestion pipelines


---

**Future Work**

Potential extensions include:



* integration with real-world OpenStreetMap ingestion pipelines
* support for polygon and line geometries
* spatiotemporal indexing
* GraphQL or richer API interfaces
* LLM-based query orchestration


---

**License**

This project is licensed under the MIT License.


---

**Suggested Citation**

Hosage Norman, C.  A Resource-Oriented Geospatial Data Model with Quad-Tree Indexing and Provenance: Toward Scalable and Reproducible GeoAI Systems.


---

**Keywords**

geospatial, GIS, GeoAI, PostGIS, quad-tree, spatial indexing, provenance, reproducibility

 
