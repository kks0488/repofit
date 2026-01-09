"""
Folder Scanner - 로컬 프로젝트 폴더 스캔 및 자동 등록

기능:
- 지정된 폴더의 프로젝트 감지
- package.json, pyproject.toml, README.md 등에서 스택 추출
- 자동 프로젝트 등록
"""

import json
import re
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib


class FolderScanner:
    """로컬 프로젝트 폴더 스캐너"""

    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path).expanduser().resolve()

        # 무시할 디렉토리
        self.ignore_dirs = {
            "node_modules", ".git", ".venv", "venv", "__pycache__",
            ".next", ".nuxt", "dist", "build", "target", ".idea",
            ".vscode", "coverage", ".pytest_cache", ".mypy_cache",
        }

    def scan(self) -> list[dict]:
        """프로젝트 폴더 스캔"""
        if not self.base_path.exists():
            raise FileNotFoundError(f"경로가 존재하지 않습니다: {self.base_path}")

        projects = []

        for item in self.base_path.iterdir():
            if not item.is_dir():
                continue

            if item.name.startswith(".") or item.name in self.ignore_dirs:
                continue

            project = self._analyze_project(item)
            if project:
                projects.append(project)

        return projects

    def _analyze_project(self, path: Path) -> dict | None:
        """프로젝트 분석"""
        # 프로젝트 감지 파일들
        indicators = [
            "package.json", "pyproject.toml", "requirements.txt",
            "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
            "README.md", "README.rst", ".git",
        ]

        has_indicator = any((path / f).exists() for f in indicators)
        if not has_indicator:
            return None

        project = {
            "name": path.name,
            "path": str(path),
            "tech_stack": [],
            "tags": [],
            "description": "",
        }

        # 스택 감지
        project["tech_stack"] = self._detect_stack(path)

        # 설명 추출
        project["description"] = self._extract_description(path)

        # 태그 추출
        project["tags"] = self._extract_tags(path)

        return project

    def _detect_stack(self, path: Path) -> list[str]:
        """tech_stack 감지"""
        stack = []

        # package.json
        package_json = path / "package.json"
        if package_json.exists():
            stack.extend(self._parse_package_json(package_json))

        # pyproject.toml
        pyproject = path / "pyproject.toml"
        if pyproject.exists():
            stack.extend(self._parse_pyproject(pyproject))

        # requirements.txt
        requirements = path / "requirements.txt"
        if requirements.exists():
            stack.extend(self._parse_requirements(requirements))

        # go.mod
        go_mod = path / "go.mod"
        if go_mod.exists():
            stack.append("go")

        # Cargo.toml
        cargo = path / "Cargo.toml"
        if cargo.exists():
            stack.append("rust")

        # 중복 제거
        return list(dict.fromkeys(stack))[:15]

    def _parse_package_json(self, path: Path) -> list[str]:
        """package.json에서 스택 추출"""
        stack = ["javascript"]

        try:
            data = json.loads(path.read_text(encoding="utf-8"))

            deps = {
                **data.get("dependencies", {}),
                **data.get("devDependencies", {}),
            }

            # 주요 프레임워크/라이브러리 매핑
            framework_map = {
                "react": "react",
                "vue": "vue",
                "angular": "angular",
                "svelte": "svelte",
                "next": "nextjs",
                "nuxt": "nuxtjs",
                "express": "express",
                "fastify": "fastify",
                "nestjs": "nestjs",
                "typescript": "typescript",
                "tailwindcss": "tailwind",
                "prisma": "prisma",
                "@supabase/supabase-js": "supabase",
            }

            for dep, tech in framework_map.items():
                if dep in deps:
                    stack.append(tech)

        except Exception:
            pass

        return stack

    def _parse_pyproject(self, path: Path) -> list[str]:
        """pyproject.toml에서 스택 추출"""
        stack = ["python"]

        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))

            deps = []
            # poetry
            if "tool" in data and "poetry" in data["tool"]:
                deps.extend(data["tool"]["poetry"].get("dependencies", {}).keys())
            # standard
            if "project" in data:
                deps.extend(data["project"].get("dependencies", []))

            # 프레임워크 매핑
            framework_map = {
                "fastapi": "fastapi",
                "django": "django",
                "flask": "flask",
                "typer": "typer",
                "langchain": "langchain",
                "openai": "openai",
                "google-genai": "gemini",
                "pytorch": "pytorch",
                "tensorflow": "tensorflow",
                "pandas": "pandas",
                "numpy": "numpy",
            }

            for dep in deps:
                dep_name = dep.split("[")[0].split(">=")[0].split("==")[0].lower()
                if dep_name in framework_map:
                    stack.append(framework_map[dep_name])

        except Exception:
            pass

        return stack

    def _parse_requirements(self, path: Path) -> list[str]:
        """requirements.txt에서 스택 추출"""
        stack = ["python"]

        try:
            content = path.read_text(encoding="utf-8")

            framework_map = {
                "fastapi": "fastapi",
                "django": "django",
                "flask": "flask",
                "langchain": "langchain",
            }

            for line in content.split("\n"):
                line = line.strip().split("#")[0].split(">=")[0].split("==")[0].lower()
                if line in framework_map:
                    stack.append(framework_map[line])

        except Exception:
            pass

        return stack

    def _extract_description(self, path: Path) -> str:
        """프로젝트 설명 추출"""
        # README.md에서 첫 번째 단락 추출
        for readme_name in ["README.md", "README.rst", "readme.md"]:
            readme = path / readme_name
            if readme.exists():
                try:
                    content = readme.read_text(encoding="utf-8")
                    # 첫 번째 헤딩 이후 첫 번째 단락
                    lines = content.split("\n")
                    desc_lines = []
                    in_desc = False

                    for line in lines:
                        if line.startswith("#"):
                            in_desc = True
                            continue
                        if in_desc:
                            if line.strip():
                                desc_lines.append(line.strip())
                            elif desc_lines:
                                break

                    if desc_lines:
                        return " ".join(desc_lines)[:200]
                except Exception:
                    pass

        # package.json description
        package_json = path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                desc = data.get("description", "")
                if desc:
                    return desc[:200]
            except Exception:
                pass

        return f"Local project: {path.name}"

    def _extract_tags(self, path: Path) -> list[str]:
        """프로젝트 태그 추출"""
        tags = []

        # package.json keywords
        package_json = path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                tags.extend(data.get("keywords", []))
            except Exception:
                pass

        # README에서 태그 추출 (## Tags 등)
        for readme_name in ["README.md", "readme.md"]:
            readme = path / readme_name
            if readme.exists():
                try:
                    content = readme.read_text(encoding="utf-8").lower()
                    # 일반적인 태그 키워드 감지
                    common_tags = ["cli", "api", "web", "mobile", "bot", "automation", "analytics", "dashboard"]
                    for tag in common_tags:
                        if tag in content:
                            tags.append(tag)
                except Exception:
                    pass

        return list(dict.fromkeys(tags))[:10]

    def sync_to_storage(self, projects: list[dict], auto_match: bool = True) -> dict:
        """스캔된 프로젝트를 스토리지에 저장"""
        from src.storage import SupabaseStorage
        storage = SupabaseStorage()

        created = 0
        skipped = 0

        for project in projects:
            # 이미 존재하는지 확인
            existing = storage.get_project_by_name(project["name"])
            if existing:
                skipped += 1
                continue

            # 프로젝트 생성
            project_data = {
                "name": project["name"],
                "description": project.get("description", ""),
                "tech_stack": project.get("tech_stack", []),
                "tags": project.get("tags", []),
            }

            storage.upsert_project(project_data)
            created += 1

        result = {
            "created": created,
            "skipped": skipped,
        }

        # 자동 매칭
        if auto_match and created > 0:
            try:
                from src.matcher import Recommender
                recommender = Recommender()
                recommender.embed_new_projects()
                match_result = recommender.run_full_pipeline(min_stars=100)
                result["recommendations"] = match_result.get("total_recommendations", 0)
            except Exception:
                pass

        return result


def scan_projects_folder(path: str = "~/projects", auto_sync: bool = True) -> dict:
    """프로젝트 폴더 스캔 헬퍼 함수"""
    scanner = FolderScanner(path)
    projects = scanner.scan()

    result = {
        "path": str(scanner.base_path),
        "projects": projects,
        "count": len(projects),
    }

    if auto_sync and projects:
        sync_result = scanner.sync_to_storage(projects)
        result.update(sync_result)

    return result
