from datetime import UTC, datetime
from uuid import UUID

from supabase import Client, create_client

from src.config import get_settings
from src.models import AnalyzedRepo


class SupabaseStorage:
    def __init__(self) -> None:
        settings = get_settings()
        self._client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_key,
        )

    def save_snapshot(
        self,
        repos: list[AnalyzedRepo],
        language: str | None = None,
        since: str = "daily",
    ) -> UUID:
        snapshot_result = (
            self._client.table("gt_snapshots")
            .insert({
                "language": language,
                "since": since,
                "repo_count": len(repos),
                "collected_at": datetime.now(UTC).isoformat(),
            })
            .execute()
        )
        snapshot_id = snapshot_result.data[0]["id"]

        for repo in repos:
            repo_data = {
                "full_name": repo.full_name,
                "owner": repo.owner,
                "name": repo.name,
                "url": repo.url,
                "description": repo.description,
                "language": repo.language,
                "license": repo.license,
                "topics": repo.topics,
                "stars": repo.stars,
                "forks": repo.forks,
                "open_issues": repo.open_issues,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            if repo.github_id is not None:
                repo_data["github_id"] = repo.github_id

            if repo.created_at:
                repo_data["first_seen_at"] = repo.created_at.isoformat()

            repo_result = (
                self._client.table("gt_repositories")
                .upsert(repo_data, on_conflict="full_name")
                .execute()
            )
            repo_id = repo_result.data[0]["id"]

            self._client.table("gt_trending_entries").insert({
                "snapshot_id": snapshot_id,
                "repository_id": repo_id,
                "rank": repo.rank,
                "stars": repo.stars,
                "stars_today": repo.stars_today,
                "forks": repo.forks,
                "is_active": repo.is_active,
            }).execute()

            if repo.summary or repo.overall_score > 0:
                self._client.table("gt_analyses").insert({
                    "repository_id": repo_id,
                    "health_score": repo.health_score,
                    "activity_score": repo.activity_score,
                    "community_score": repo.community_score,
                    "documentation_score": repo.documentation_score,
                    "overall_score": repo.overall_score,
                    "summary": repo.summary,
                    "use_cases": repo.use_cases,
                    "integration_tips": repo.integration_tips,
                    "potential_risks": repo.potential_risks,
                    "model_used": get_settings().gemini_model,
                    "analyzed_at": repo.analyzed_at.isoformat() if repo.analyzed_at else None,
                }).execute()

        return UUID(snapshot_id)

    def upsert_repositories(self, repos: list[AnalyzedRepo]) -> list[str]:
        now = datetime.now(UTC)
        repo_ids: list[str] = []

        for repo in repos:
            repo_data = {
                "full_name": repo.full_name,
                "owner": repo.owner,
                "name": repo.name,
                "url": repo.url,
                "description": repo.description,
                "language": repo.language,
                "license": repo.license,
                "topics": repo.topics,
                "stars": repo.stars,
                "forks": repo.forks,
                "open_issues": repo.open_issues,
                "updated_at": now.isoformat(),
            }

            if repo.github_id is not None:
                repo_data["github_id"] = repo.github_id

            if repo.created_at:
                repo_data["first_seen_at"] = repo.created_at.isoformat()

            repo_result = (
                self._client.table("gt_repositories")
                .upsert(repo_data, on_conflict="full_name")
                .execute()
            )
            repo_id = repo_result.data[0]["id"]
            repo_ids.append(repo_id)

            if repo.summary or repo.overall_score > 0:
                self._client.table("gt_analyses").insert({
                    "repository_id": repo_id,
                    "health_score": repo.health_score,
                    "activity_score": repo.activity_score,
                    "community_score": repo.community_score,
                    "documentation_score": repo.documentation_score,
                    "overall_score": repo.overall_score,
                    "summary": repo.summary,
                    "use_cases": repo.use_cases,
                    "integration_tips": repo.integration_tips,
                    "potential_risks": repo.potential_risks,
                    "model_used": get_settings().gemini_model,
                    "analyzed_at": repo.analyzed_at.isoformat() if repo.analyzed_at else None,
                }).execute()

        return repo_ids

    def get_latest_trending(self, language: str | None = None, limit: int = 25) -> list[dict]:
        query = self._client.table("gt_v_latest_trending").select("*")
        if language:
            query = query.eq("language", language)
        return query.limit(limit).execute().data

    def get_repo_metadata_by_ids(self, repo_ids: list[str]) -> dict[str, dict]:
        if not repo_ids:
            return {}

        repos = (
            self._client.table("gt_repositories")
            .select("id, full_name, language, topics, stars")
            .in_("id", repo_ids)
            .execute()
            .data
        )

        analyses = (
            self._client.table("gt_analyses")
            .select("repository_id, overall_score, analyzed_at")
            .in_("repository_id", repo_ids)
            .order("analyzed_at", desc=True)
            .execute()
            .data
        )

        trending = (
            self._client.table("gt_v_latest_trending")
            .select("id, stars_today")
            .in_("id", repo_ids)
            .execute()
            .data
        )

        analysis_map: dict[str, dict] = {}
        for analysis in analyses:
            repo_id = analysis.get("repository_id")
            if repo_id and repo_id not in analysis_map:
                analysis_map[repo_id] = analysis

        trending_map = {row.get("id"): row for row in trending if row.get("id")}

        repo_map: dict[str, dict] = {}
        for repo in repos:
            repo["overall_score"] = analysis_map.get(repo["id"], {}).get("overall_score")
            repo["stars_today"] = trending_map.get(repo["id"], {}).get("stars_today", 0)
            repo_map[repo["id"]] = repo

        return repo_map

    def get_repo_history(self, full_name: str, limit: int = 30) -> list[dict]:
        repo = self._client.table("gt_repositories").select("id").eq("full_name", full_name).single().execute()
        if not repo.data:
            return []
        return (
            self._client.table("gt_trending_entries")
            .select("*, gt_snapshots(collected_at)")
            .eq("repository_id", repo.data["id"])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )

    def get_snapshots(self, limit: int = 10) -> list[dict]:
        return (
            self._client.table("gt_snapshots")
            .select("*")
            .order("collected_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )

    # ==================== PROJECT MANAGEMENT ====================

    def create_project(
        self,
        name: str,
        description: str | None = None,
        tech_stack: list[str] | None = None,
        tags: list[str] | None = None,
        goals: str | None = None,
        readme_content: str | None = None,
    ) -> dict:
        return (
            self._client.table("gt_my_projects")
            .insert({
                "name": name,
                "description": description,
                "tech_stack": tech_stack or [],
                "tags": tags or [],
                "goals": goals,
                "readme_content": readme_content,
            })
            .execute()
            .data[0]
        )

    def get_projects(self, active_only: bool = True) -> list[dict]:
        query = self._client.table("gt_my_projects").select("*")
        if active_only:
            query = query.eq("is_active", True)
        return query.order("created_at", desc=True).execute().data

    def get_project(self, project_id: str) -> dict | None:
        result = self._client.table("gt_my_projects").select("*").eq("id", project_id).single().execute()
        return result.data if result.data else None

    def update_project_embedding(self, project_id: str, embedding: list[float]) -> None:
        self._client.table("gt_my_projects").update({
            "embedding": embedding,
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", project_id).execute()

    def update_repo_embedding(self, repo_id: str, embedding: list[float]) -> None:
        self._client.table("gt_repositories").update({
            "embedding": embedding,
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", repo_id).execute()

    # ==================== RECOMMENDATIONS ====================

    def get_recommendations(self, project_id: str | None = None, limit: int = 20) -> list[dict]:
        query = self._client.table("gt_v_recommendations").select("*")
        if project_id:
            query = query.eq("project_id", project_id)
        return query.limit(limit).execute().data

    def save_recommendation(
        self,
        project_id: str,
        repository_id: str,
        score: float,
        reasons: list[dict],
        embedding_similarity: float | None = None,
        stack_overlap_score: float | None = None,
    ) -> dict:
        return (
            self._client.table("gt_recommendations")
            .upsert({
                "project_id": project_id,
                "repository_id": repository_id,
                "score": score,
                "reasons": reasons,
                "embedding_similarity": embedding_similarity,
                "stack_overlap_score": stack_overlap_score,
                "status": "new",
            }, on_conflict="project_id,repository_id")
            .execute()
            .data[0]
        )

    def dismiss_recommendation(self, recommendation_id: str) -> None:
        self._client.table("gt_recommendations").update({
            "status": "dismissed",
            "dismissed_at": datetime.now(UTC).isoformat(),
        }).eq("id", recommendation_id).execute()

    def save_feedback(self, recommendation_id: str, feedback_type: str, note: str | None = None) -> dict:
        return (
            self._client.table("gt_feedback")
            .insert({
                "recommendation_id": recommendation_id,
                "feedback_type": feedback_type,
                "note": note,
            })
            .execute()
            .data[0]
        )

    # ==================== BOOKMARKS ====================

    def add_bookmark(self, repository_id: str, project_id: str | None = None, notes: str | None = None) -> dict:
        return (
            self._client.table("gt_bookmarks")
            .upsert({
                "repository_id": repository_id,
                "project_id": project_id,
                "notes": notes,
                "status": "saved",
            }, on_conflict="repository_id,project_id")
            .execute()
            .data[0]
        )

    def get_bookmarks(self, project_id: str | None = None) -> list[dict]:
        query = (
            self._client.table("gt_bookmarks")
            .select("*, gt_repositories(*)")
        )
        if project_id:
            query = query.eq("project_id", project_id)
        return query.order("created_at", desc=True).execute().data

    def remove_bookmark(self, bookmark_id: str) -> None:
        self._client.table("gt_bookmarks").delete().eq("id", bookmark_id).execute()

    # ==================== VECTOR SEARCH ====================

    def find_similar_repos(self, project_id: str, limit: int = 10, min_stars: int = 100) -> list[dict]:
        return self._client.rpc(
            "gt_match_repos_to_project",
            {"p_project_id": project_id, "p_limit": limit, "p_min_stars": min_stars}
        ).execute().data

    def get_repos_without_embedding(self, limit: int = 50) -> list[dict]:
        return (
            self._client.table("gt_repositories")
            .select("id, full_name, description, readme_summary, topics")
            .is_("embedding", "null")
            .limit(limit)
            .execute()
            .data
        )

    def get_projects_without_embedding(self) -> list[dict]:
        return (
            self._client.table("gt_my_projects")
            .select("id, name, description, tech_stack, tags, goals, readme_content")
            .is_("embedding", "null")
            .execute()
            .data
        )

    # ==================== AUTO-DISCOVERY SUPPORT ====================

    def get_project_by_name(self, name: str) -> dict | None:
        """Get project by name."""
        result = (
            self._client.table("gt_my_projects")
            .select("*")
            .eq("name", name)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def upsert_project(self, project_data: dict) -> dict:
        """Insert a project (for github-sync and folder-scan)."""
        return (
            self._client.table("gt_my_projects")
            .insert(project_data)
            .execute()
            .data[0]
        )

    def get_repository_by_name(self, full_name: str) -> dict | None:
        """Get repository by full_name (owner/repo)."""
        result = (
            self._client.table("gt_repositories")
            .select("*")
            .eq("full_name", full_name)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def search_similar_repos(self, embedding: list[float], limit: int = 5) -> list[dict]:
        """Search for similar repos using vector similarity."""
        try:
            return self._client.rpc(
                "gt_search_similar_repos",
                {"query_embedding": embedding, "match_count": limit}
            ).execute().data
        except Exception:
            # Fallback: return latest trending if RPC fails
            return self.get_latest_trending(limit=limit)
