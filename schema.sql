-- GitHub Trending Analyzer Database Schema v2
-- Isolated with gt_ prefix + pgvector for smart matching

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

------------------------------------------------------------
-- CORE TABLES (gt_ prefix for isolation)
------------------------------------------------------------

-- Trending snapshots (tracks each collection run)
CREATE TABLE IF NOT EXISTS gt_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    language VARCHAR(50),
    since VARCHAR(20) NOT NULL DEFAULT 'daily',
    repo_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Repositories (unique repos we've seen)
CREATE TABLE IF NOT EXISTS gt_repositories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    github_id BIGINT UNIQUE,
    full_name VARCHAR(255) NOT NULL UNIQUE,
    owner VARCHAR(100) NOT NULL,
    name VARCHAR(155) NOT NULL,
    url TEXT NOT NULL,
    description TEXT,
    readme_summary TEXT,
    language VARCHAR(50),
    license VARCHAR(50),
    topics TEXT[],
    stars INT DEFAULT 0,
    forks INT DEFAULT 0,
    open_issues INT DEFAULT 0,
    stars_growth_7d INT DEFAULT 0,
    embedding vector(768),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trending entries (each time a repo appears in trending)
CREATE TABLE IF NOT EXISTS gt_trending_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_id UUID NOT NULL REFERENCES gt_snapshots(id) ON DELETE CASCADE,
    repository_id UUID NOT NULL REFERENCES gt_repositories(id) ON DELETE CASCADE,
    rank INT NOT NULL,
    stars INT NOT NULL DEFAULT 0,
    stars_today INT NOT NULL DEFAULT 0,
    forks INT NOT NULL DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(snapshot_id, repository_id)
);

-- AI analysis results
CREATE TABLE IF NOT EXISTS gt_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repository_id UUID NOT NULL REFERENCES gt_repositories(id) ON DELETE CASCADE,
    health_score INT DEFAULT 0,
    activity_score INT DEFAULT 0,
    community_score INT DEFAULT 0,
    documentation_score INT DEFAULT 0,
    overall_score INT DEFAULT 0,
    summary TEXT,
    use_cases TEXT[],
    integration_tips TEXT,
    potential_risks TEXT[],
    model_used VARCHAR(100),
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

------------------------------------------------------------
-- PROJECT MATCHING TABLES (Smart Recommendations)
------------------------------------------------------------

-- User's projects to match against trending
CREATE TABLE IF NOT EXISTS gt_my_projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    tech_stack TEXT[] DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    goals TEXT,
    readme_content TEXT,
    embedding vector(768),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Project documentation chunks (for detailed matching)
CREATE TABLE IF NOT EXISTS gt_project_docs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES gt_my_projects(id) ON DELETE CASCADE,
    source VARCHAR(100),
    title VARCHAR(255),
    content TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Recommendations (trending repo → my project matches)
CREATE TABLE IF NOT EXISTS gt_recommendations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES gt_my_projects(id) ON DELETE CASCADE,
    repository_id UUID NOT NULL REFERENCES gt_repositories(id) ON DELETE CASCADE,
    score FLOAT NOT NULL DEFAULT 0,
    embedding_similarity FLOAT,
    stack_overlap_score FLOAT,
    reasons JSONB DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'new',
    dismissed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, repository_id)
);

-- User feedback on recommendations
CREATE TABLE IF NOT EXISTS gt_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recommendation_id UUID NOT NULL REFERENCES gt_recommendations(id) ON DELETE CASCADE,
    feedback_type VARCHAR(20) NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Bookmarks (saved repos for later)
CREATE TABLE IF NOT EXISTS gt_bookmarks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repository_id UUID NOT NULL REFERENCES gt_repositories(id) ON DELETE CASCADE,
    project_id UUID REFERENCES gt_my_projects(id) ON DELETE SET NULL,
    notes TEXT,
    status VARCHAR(20) DEFAULT 'saved',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(repository_id, project_id)
);

------------------------------------------------------------
-- INDEXES
------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_gt_repos_full_name ON gt_repositories(full_name);
CREATE INDEX IF NOT EXISTS idx_gt_repos_language ON gt_repositories(language);
CREATE INDEX IF NOT EXISTS idx_gt_repos_stars ON gt_repositories(stars DESC);
CREATE INDEX IF NOT EXISTS idx_gt_entries_snapshot ON gt_trending_entries(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_gt_entries_repo ON gt_trending_entries(repository_id);
CREATE INDEX IF NOT EXISTS idx_gt_snapshots_date ON gt_snapshots(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_gt_analyses_repo ON gt_analyses(repository_id);
CREATE INDEX IF NOT EXISTS idx_gt_analyses_score ON gt_analyses(overall_score DESC);
CREATE INDEX IF NOT EXISTS idx_gt_recommendations_project ON gt_recommendations(project_id);
CREATE INDEX IF NOT EXISTS idx_gt_recommendations_score ON gt_recommendations(score DESC);
CREATE INDEX IF NOT EXISTS idx_gt_bookmarks_repo ON gt_bookmarks(repository_id);

-- Vector similarity indexes (HNSW for fast approximate search)
CREATE INDEX IF NOT EXISTS idx_gt_repos_embedding ON gt_repositories 
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_gt_projects_embedding ON gt_my_projects 
    USING hnsw (embedding vector_cosine_ops);

------------------------------------------------------------
-- VIEWS
------------------------------------------------------------

-- Latest trending with analysis
CREATE OR REPLACE VIEW gt_v_latest_trending AS
SELECT 
    r.id,
    r.full_name,
    r.description,
    r.language,
    r.license,
    r.topics,
    r.stars,
    r.forks,
    te.rank,
    te.stars_today,
    te.is_active,
    a.overall_score,
    a.health_score,
    a.summary,
    a.use_cases,
    a.integration_tips,
    s.collected_at
FROM gt_trending_entries te
JOIN gt_repositories r ON r.id = te.repository_id
JOIN gt_snapshots s ON s.id = te.snapshot_id
LEFT JOIN gt_analyses a ON a.repository_id = r.id
WHERE s.id = (
    SELECT id FROM gt_snapshots 
    ORDER BY collected_at DESC 
    LIMIT 1
)
ORDER BY te.rank;

-- Recommendations with repo details
CREATE OR REPLACE VIEW gt_v_recommendations AS
SELECT 
    rec.id as recommendation_id,
    rec.score,
    rec.reasons,
    rec.status,
    rec.created_at as recommended_at,
    p.id as project_id,
    p.name as project_name,
    p.tech_stack as project_stack,
    r.id as repo_id,
    r.full_name,
    r.description,
    r.language,
    r.topics,
    r.stars,
    r.stars_growth_7d,
    a.overall_score,
    a.summary
FROM gt_recommendations rec
JOIN gt_my_projects p ON p.id = rec.project_id
JOIN gt_repositories r ON r.id = rec.repository_id
LEFT JOIN gt_analyses a ON a.repository_id = r.id
WHERE rec.status != 'dismissed'
ORDER BY rec.score DESC;

------------------------------------------------------------
-- FUNCTIONS
------------------------------------------------------------

-- Find similar repos to a project using vector similarity
CREATE OR REPLACE FUNCTION gt_match_repos_to_project(
    p_project_id UUID,
    p_limit INT DEFAULT 10,
    p_min_stars INT DEFAULT 100
)
RETURNS TABLE (
    repository_id UUID,
    full_name TEXT,
    similarity FLOAT,
    stars INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        r.id,
        r.full_name::TEXT,
        1 - (r.embedding <=> p.embedding) as similarity,
        r.stars
    FROM gt_repositories r
    CROSS JOIN gt_my_projects p
    WHERE p.id = p_project_id
      AND r.embedding IS NOT NULL
      AND p.embedding IS NOT NULL
      AND r.stars >= p_min_stars
    ORDER BY r.embedding <=> p.embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

------------------------------------------------------------
-- RLS POLICIES
------------------------------------------------------------

ALTER TABLE gt_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE gt_repositories ENABLE ROW LEVEL SECURITY;
ALTER TABLE gt_trending_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE gt_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE gt_my_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE gt_project_docs ENABLE ROW LEVEL SECURITY;
ALTER TABLE gt_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE gt_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE gt_bookmarks ENABLE ROW LEVEL SECURITY;

-- Allow anonymous read for trending data
CREATE POLICY "anon_read_snapshots" ON gt_snapshots FOR SELECT USING (true);
CREATE POLICY "anon_read_repos" ON gt_repositories FOR SELECT USING (true);
CREATE POLICY "anon_read_entries" ON gt_trending_entries FOR SELECT USING (true);
CREATE POLICY "anon_read_analyses" ON gt_analyses FOR SELECT USING (true);
CREATE POLICY "anon_read_projects" ON gt_my_projects FOR SELECT USING (true);
CREATE POLICY "anon_read_recommendations" ON gt_recommendations FOR SELECT USING (true);
CREATE POLICY "anon_read_bookmarks" ON gt_bookmarks FOR SELECT USING (true);

-- Optional: allow anonymous writes for single-user/local setups
CREATE POLICY "anon_insert_projects" ON gt_my_projects FOR INSERT WITH CHECK (true);
CREATE POLICY "anon_insert_bookmarks" ON gt_bookmarks FOR INSERT WITH CHECK (true);
CREATE POLICY "anon_delete_bookmarks" ON gt_bookmarks FOR DELETE USING (true);

-- Service role full access
CREATE POLICY "service_all_snapshots" ON gt_snapshots FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_all_repos" ON gt_repositories FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_all_entries" ON gt_trending_entries FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_all_analyses" ON gt_analyses FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_all_projects" ON gt_my_projects FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_all_docs" ON gt_project_docs FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_all_recommendations" ON gt_recommendations FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_all_feedback" ON gt_feedback FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_all_bookmarks" ON gt_bookmarks FOR ALL USING (auth.role() = 'service_role');
