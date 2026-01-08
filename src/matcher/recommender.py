from typing import Optional
from datetime import datetime, timezone

from src.storage import SupabaseStorage
from src.embedder.gemini_embedder import (
    embed_text,
    create_repo_summary,
    create_project_summary,
)
from src.notifier import SlackNotifier


class Recommender:
    def __init__(self) -> None:
        self.storage = SupabaseStorage()

    def _calculate_stack_overlap(
        self,
        project_stack: list[str],
        project_tags: list[str],
        repo_language: Optional[str],
        repo_topics: list[str],
    ) -> tuple[float, list[str]]:
        project_terms = set(t.lower() for t in project_stack + project_tags)
        repo_terms = set(t.lower() for t in repo_topics)
        if repo_language:
            repo_terms.add(repo_language.lower())

        if not project_terms or not repo_terms:
            return 0.0, []

        overlap = project_terms & repo_terms
        overlap_score = len(overlap) / max(len(project_terms), 1)
        return min(1.0, overlap_score), list(overlap)

    def embed_new_repos(self, limit: int = 50) -> int:
        repos = self.storage.get_repos_without_embedding(limit)
        count = 0
        for repo in repos:
            summary = create_repo_summary(
                full_name=repo["full_name"],
                description=repo.get("description"),
                language=repo.get("language"),
                topics=repo.get("topics", []),
                readme_summary=repo.get("readme_summary"),
            )
            try:
                embedding = embed_text(summary)
                self.storage.update_repo_embedding(repo["id"], embedding)
                count += 1
            except Exception:
                continue
        return count

    def embed_new_projects(self) -> int:
        projects = self.storage.get_projects_without_embedding()
        count = 0
        for project in projects:
            summary = create_project_summary(
                name=project["name"],
                description=project.get("description"),
                tech_stack=project.get("tech_stack", []),
                tags=project.get("tags", []),
                goals=project.get("goals"),
                readme_excerpt=project.get("readme_content"),
            )
            try:
                embedding = embed_text(summary)
                self.storage.update_project_embedding(project["id"], embedding)
                count += 1
            except Exception:
                continue
        return count

    def match_project_to_repos(
        self,
        project_id: str,
        min_stars: int = 100,
        limit: int = 20,
    ) -> list[dict]:
        project = self.storage.get_project(project_id)
        if not project:
            return []

        similar_repos = self.storage.find_similar_repos(
            project_id=project_id,
            limit=limit * 2,
            min_stars=min_stars,
        )

        recommendations = []
        for repo_match in similar_repos:
            repo_id = repo_match["repository_id"]
            full_name = repo_match["full_name"]
            embedding_sim = repo_match["similarity"]

            trending = self.storage.get_latest_trending(limit=100)
            repo_data = next((t for t in trending if t["full_name"] == full_name), None)

            if not repo_data:
                continue

            stack_score, overlaps = self._calculate_stack_overlap(
                project_stack=project.get("tech_stack", []),
                project_tags=project.get("tags", []),
                repo_language=repo_data.get("language"),
                repo_topics=repo_data.get("topics", []),
            )

            final_score = (
                0.5 * embedding_sim +
                0.3 * stack_score +
                0.2 * min(1.0, (repo_data.get("overall_score", 50) / 100))
            )

            reasons = []
            if embedding_sim > 0.7:
                reasons.append({"type": "semantic", "text": "Semantically similar to your project"})
            if overlaps:
                reasons.append({"type": "stack", "text": f"Stack overlap: {', '.join(overlaps)}"})
            if repo_data.get("stars_today", 0) > 100:
                reasons.append({"type": "trending", "text": f"Hot today: +{repo_data['stars_today']} stars"})

            self.storage.save_recommendation(
                project_id=project_id,
                repository_id=repo_id,
                score=final_score,
                reasons=reasons,
                embedding_similarity=embedding_sim,
                stack_overlap_score=stack_score,
            )

            recommendations.append({
                "repo_id": repo_id,
                "full_name": full_name,
                "score": final_score,
                "reasons": reasons,
            })

        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations[:limit]

    def run_full_pipeline(
        self,
        min_stars: int = 100,
        notify: bool = False,
        score_threshold: float = 0.7,
    ) -> dict:
        repos_embedded = self.embed_new_repos()
        projects_embedded = self.embed_new_projects()

        projects = self.storage.get_projects()
        all_recommendations: list[dict] = []
        total_recommendations = 0

        for project in projects:
            recs = self.match_project_to_repos(
                project_id=project["id"],
                min_stars=min_stars,
            )
            for r in recs:
                r["project_name"] = project.get("name", "")
            all_recommendations.extend(recs)
            total_recommendations += len(recs)

        notified_count = 0
        if notify:
            high_score_recs = [
                r for r in all_recommendations
                if r.get("score", 0) >= score_threshold
            ]
            if high_score_recs:
                notifier = SlackNotifier()
                if notifier.notify_recommendations(
                    recommendations=high_score_recs,
                    threshold=score_threshold,
                ):
                    notified_count = len(high_score_recs)

        return {
            "repos_embedded": repos_embedded,
            "projects_embedded": projects_embedded,
            "projects_matched": len(projects),
            "total_recommendations": total_recommendations,
            "notified_count": notified_count,
        }


def run_matching_pipeline(
    min_stars: int = 100,
    notify: bool = False,
    score_threshold: float = 0.7,
) -> dict:
    recommender = Recommender()
    return recommender.run_full_pipeline(
        min_stars=min_stars,
        notify=notify,
        score_threshold=score_threshold,
    )
