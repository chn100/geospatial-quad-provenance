CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP TABLE IF EXISTS search_result_edges CASCADE;
DROP TABLE IF EXISTS search_runs CASCADE;
DROP TABLE IF EXISTS provenance_edges CASCADE;
DROP TABLE IF EXISTS provenance_events CASCADE;
DROP TABLE IF EXISTS spatial_index_entries CASCADE;
DROP TABLE IF EXISTS features CASCADE;
DROP TABLE IF EXISTS assets CASCADE;
DROP TABLE IF EXISTS collections CASCADE;

CREATE TABLE collections (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_id TEXT REFERENCES collections(id),
  uri TEXT NOT NULL,
  format TEXT NOT NULL,
  checksum TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE features (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_id TEXT NOT NULL REFERENCES collections(id),
  feature_type TEXT NOT NULL,
  name TEXT NOT NULL,
  properties JSONB NOT NULL DEFAULT '{}'::jsonb,
  geom geometry(Point, 4326) NOT NULL,
  bbox geometry(Polygon, 4326) GENERATED ALWAYS AS (ST_Envelope(geom)) STORED,
  version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active',
  source_asset_id UUID REFERENCES assets(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX features_geom_gist ON features USING GIST (geom);
CREATE INDEX features_collection_idx ON features (collection_id);
CREATE INDEX features_properties_gin ON features USING GIN (properties);

CREATE TABLE spatial_index_entries (
  feature_id UUID NOT NULL REFERENCES features(id) ON DELETE CASCADE,
  quadkey TEXT NOT NULL,
  level INTEGER NOT NULL,
  coverage_type TEXT NOT NULL CHECK (coverage_type IN ('centroid', 'intersects', 'full_cover')),
  is_primary BOOLEAN NOT NULL DEFAULT false,
  cell_bbox geometry(Polygon, 4326) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (feature_id, quadkey, level)
);

CREATE INDEX spatial_quadkey_idx ON spatial_index_entries (level, quadkey);
CREATE INDEX spatial_feature_idx ON spatial_index_entries (feature_id);
CREATE INDEX spatial_cell_gist ON spatial_index_entries USING GIST (cell_bbox);

CREATE TABLE provenance_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  activity_type TEXT NOT NULL,
  started_at TIMESTAMPTZ DEFAULT now(),
  ended_at TIMESTAMPTZ,
  agent JSONB NOT NULL DEFAULT '{}'::jsonb,
  parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
  quality_metrics JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE provenance_edges (
  provenance_event_id UUID NOT NULL REFERENCES provenance_events(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('used', 'generated')),
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  PRIMARY KEY (provenance_event_id, role, entity_type, entity_id)
);

CREATE TABLE search_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_text TEXT NOT NULL,
  center geometry(Point, 4326) NOT NULL,
  radius_meters DOUBLE PRECISION NOT NULL,
  property_filters JSONB NOT NULL DEFAULT '{}'::jsonb,
  quad_levels INTEGER[] NOT NULL,
  candidate_count INTEGER,
  validated_count INTEGER,
  rejected_count INTEGER,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE search_result_edges (
  search_run_id UUID NOT NULL REFERENCES search_runs(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('used_quadkey', 'candidate', 'validated', 'rejected')),
  entity_id TEXT NOT NULL,
  reason TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  PRIMARY KEY (search_run_id, role, entity_id)
);
