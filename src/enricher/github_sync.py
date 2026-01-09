"""
GitHub Account Sync - 사용자의 GitHub 레포를 프로젝트로 동기화

기능:
- 사용자의 GitHub 레포 목록 가져오기
- 언어/토픽에서 tech_stack 자동 추출
- 프로젝트로 자동 등록
"""

import httpx

from src.config import get_settings


def get_authenticated_user(token: str) -> dict | None:
    """인증된 사용자 정보 가져오기"""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get("https://api.github.com/user", headers=headers)
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass

    return None


def get_user_repos(token: str, username: str = None, include_private: bool = True) -> list[dict]:
    """사용자의 레포 목록 가져오기"""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    repos = []
    page = 1

    try:
        with httpx.Client(timeout=30) as client:
            while True:
                # 인증된 사용자의 레포 가져오기
                url = "https://api.github.com/user/repos"
                params = {
                    "page": page,
                    "per_page": 100,
                    "sort": "updated",
                    "direction": "desc",
                }

                if not include_private:
                    params["visibility"] = "public"

                response = client.get(url, headers=headers, params=params)

                if response.status_code != 200:
                    break

                page_repos = response.json()
                if not page_repos:
                    break

                repos.extend(page_repos)
                page += 1

                if len(page_repos) < 100:
                    break

    except Exception as e:
        print(f"레포 가져오기 실패: {e}")

    return repos


def get_starred_repos(token: str, limit: int = 50) -> list[dict]:
    """사용자가 스타한 레포 목록 가져오기"""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    repos = []

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                "https://api.github.com/user/starred",
                headers=headers,
                params={"per_page": limit, "sort": "created", "direction": "desc"},
            )

            if response.status_code == 200:
                repos = response.json()

    except Exception as e:
        print(f"스타 레포 가져오기 실패: {e}")

    return repos


def extract_tech_stack(repo: dict) -> list[str]:
    """레포에서 tech_stack 추출"""
    stack = []

    # 메인 언어
    language = repo.get("language")
    if language:
        stack.append(language.lower())

    # 토픽에서 추출
    topics = repo.get("topics", [])
    tech_keywords = {
        "react", "vue", "angular", "svelte", "nextjs", "nuxtjs",
        "fastapi", "django", "flask", "express", "nestjs",
        "typescript", "javascript", "python", "rust", "go", "java",
        "postgresql", "mongodb", "redis", "mysql", "sqlite",
        "docker", "kubernetes", "aws", "gcp", "azure",
        "graphql", "rest", "api", "websocket",
        "tailwind", "bootstrap", "sass", "css",
        "tensorflow", "pytorch", "langchain", "openai", "gemini",
    }

    for topic in topics:
        topic_lower = topic.lower()
        if topic_lower in tech_keywords:
            if topic_lower not in stack:
                stack.append(topic_lower)

    return stack[:10]


def extract_tags(repo: dict) -> list[str]:
    """레포에서 tags 추출"""
    tags = []

    # 토픽에서 추출 (tech_keywords 아닌 것들)
    topics = repo.get("topics", [])
    tech_keywords = {
        "react", "vue", "angular", "svelte", "nextjs", "nuxtjs",
        "fastapi", "django", "flask", "express", "nestjs",
        "typescript", "javascript", "python", "rust", "go", "java",
        "postgresql", "mongodb", "redis", "mysql", "sqlite",
        "docker", "kubernetes", "aws", "gcp", "azure",
    }

    for topic in topics:
        topic_lower = topic.lower()
        if topic_lower not in tech_keywords:
            tags.append(topic_lower)

    # 레포 특성에서 태그 추가
    if repo.get("fork"):
        tags.append("fork")
    if repo.get("archived"):
        tags.append("archived")
    if repo.get("is_template"):
        tags.append("template")

    return tags[:10]


def sync_github_repos(
    token: str = None,
    include_starred: bool = False,
    include_private: bool = True,
) -> dict:
    """GitHub 레포를 프로젝트로 동기화

    Returns:
        {
            "user": str,
            "repos": list[dict],  # 가져온 레포 목록
            "created": int,       # 새로 생성된 프로젝트 수
            "skipped": int,       # 이미 존재하는 프로젝트 수
            "starred": list[dict] | None,  # 스타 레포 (옵션)
        }
    """
    settings = get_settings()
    token = token or settings.github_token

    if not token:
        raise ValueError("GITHUB_TOKEN이 설정되지 않았습니다")

    # 사용자 정보
    user = get_authenticated_user(token)
    if not user:
        raise ValueError("GitHub 인증 실패")

    username = user.get("login")

    # 레포 가져오기
    repos = get_user_repos(token, username, include_private)

    # 프로젝트로 변환
    from src.storage import SupabaseStorage
    storage = SupabaseStorage()

    created = 0
    skipped = 0

    for repo in repos:
        full_name = repo.get("full_name", "")
        name = repo.get("name", "")

        # 이미 존재하는지 확인
        existing = storage.get_project_by_name(name)
        if existing:
            skipped += 1
            continue

        # 프로젝트 생성
        project_data = {
            "name": name,
            "description": repo.get("description") or f"GitHub: {full_name}",
            "tech_stack": extract_tech_stack(repo),
            "tags": extract_tags(repo),
        }

        storage.upsert_project(project_data)
        created += 1

    result = {
        "user": username,
        "repos": repos,
        "created": created,
        "skipped": skipped,
    }

    # 스타 레포
    if include_starred:
        starred = get_starred_repos(token)
        result["starred"] = starred

    return result
