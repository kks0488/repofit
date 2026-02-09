from src.config import get_settings


def build_github_api_headers(
    token: str | None = None,
    user_agent: str | None = None,
) -> dict[str, str]:
    settings = get_settings()
    github_token = settings.github_token if token is None else token

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if user_agent:
        headers["User-Agent"] = user_agent
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    return headers
