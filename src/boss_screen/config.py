"""读仓库根 boss.yaml。路径相对这份配置所在目录。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from boss_screen.rules import slug

UNLIMITED = "0"
REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_PATH = REPO_ROOT / "boss.yaml"


@dataclass(frozen=True)
class Settings:
    keywords: list[str]
    city_codes: list[str]
    job_type_name: str
    job_type_code: str
    experience: list[str]
    degree: list[str]
    salary: list[str]
    scale: list[str]
    industry: list[str]
    stage_codes: list[str]
    wait_time: int
    keyword_gap: int
    detail_limit: int
    stop_on_risk: bool
    screen_dir: Path
    browser_data: Path
    opened_chats: Path
    resume_image: Path
    greeting: str
    config_path: Path
    ai_base: str
    ai_key: str
    ai_model: str
    company_tokens: list[str]
    job_tokens: list[str]
    black_companies: list[str]
    black_jobs: list[str]
    black_recruiters: list[str]
    profile: str
    title_prompt: str
    jd_prompt: str

    def rule_kwargs(self) -> dict:
        return {
            "black_jobs": self.black_jobs,
            "black_companies": self.black_companies,
            "black_recruiters": self.black_recruiters,
            "company_tokens": self.company_tokens,
            "job_tokens": self.job_tokens,
        }


def load_settings(path: Path | None = None) -> Settings:
    yaml_path = path or YAML_PATH
    root = yaml_path.parent
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{yaml_path} 不是一份配置")
    codes = data.get("codes") or {}
    keywords = _strings(data.get("keywords"))
    if not keywords:
        raise SystemExit("boss.yaml 的 keywords 不能为空")
    city_codes = [_code(codes, "city", name) for name in _strings(data.get("cities"))]
    if not city_codes:
        raise SystemExit("boss.yaml 的 cities 不能为空，且须能对应 codes.city")
    job_type_name = str(data.get("jobType") or "").strip()
    job_type_code = _code(codes, "jobType", job_type_name) if job_type_name else UNLIMITED
    ai = data.get("ai") or {}
    base = str(ai.get("baseUrl") or "").strip()
    key = str(ai.get("apiKey") or "").strip()
    model = str(ai.get("model") or "").strip()
    if not base or not key or not model:
        raise SystemExit("boss.yaml 的 ai.baseUrl / ai.apiKey / ai.model 不能为空")
    prompts = data.get("prompts") or {}
    title = str(prompts.get("title") or "")
    jd = str(prompts.get("jd") or "")
    if not title.strip() or not jd.strip():
        raise SystemExit("boss.yaml 的 prompts.title / prompts.jd 不能为空")
    rules = data.get("rules") or {}
    black = data.get("blacklist") or {}
    # screenArchiveDir 只给对照页，续跑不读。
    screen_raw = str(data.get("screenResultsDir") or "screen-results").strip()
    gap = data.get("keywordGapSeconds")
    return Settings(
        keywords=keywords,
        city_codes=city_codes,
        job_type_name=job_type_name or "na",
        job_type_code=job_type_code,
        experience=_codes(codes, "experience", data.get("experience")),
        degree=_codes(codes, "degree", data.get("degree")),
        salary=_codes(codes, "salary", data.get("salary")),
        scale=_codes(codes, "scale", data.get("scale")),
        industry=_codes(codes, "industry", data.get("industry")),
        stage_codes=_codes(codes, "stage", data.get("stage")),
        wait_time=_wait_time(data.get("waitTime")),
        keyword_gap=300 if gap is None else max(0, int(gap)),
        detail_limit=0 if data.get("detailLimit") is None else int(data["detailLimit"]),
        stop_on_risk=str(data.get("onRisk") or "stop").strip().lower() == "stop",
        screen_dir=(root / screen_raw).resolve(),
        browser_data=(root / "browser-data").resolve(),
        opened_chats=(root / "opened-chats.jsonl").resolve(),
        resume_image=(root / "resume.jpg").resolve(),
        greeting=str(data.get("greeting") or "").strip(),
        config_path=yaml_path,
        ai_base=base.rstrip("/"),
        ai_key=key,
        ai_model=model,
        company_tokens=_strings((rules or {}).get("companyTokens")),
        job_tokens=_strings((rules or {}).get("jobTitleTokens")),
        black_companies=_strings((black or {}).get("companies")),
        black_jobs=_strings((black or {}).get("jobs")),
        black_recruiters=_strings((black or {}).get("recruiters")),
        profile=str(data.get("candidateProfile") or "").strip()
        or "杭州/上海 Python / AI 实习。Agent、LLM 应用优先。城市只分页不淘汰。",
        title_prompt=title,
        jd_prompt=jd,
    )


def fill(template: str, variables: dict[str, str]) -> str:
    text = template or ""
    for key, value in variables.items():
        text = text.replace("{" + key + "}", value or "")
    return text


def search_url(settings: Settings, city_code: str) -> str:
    params: list[str] = []
    _add(params, "city", city_code)
    _add(params, "jobType", settings.job_type_code)
    _add_list(params, "salary", settings.salary)
    _add_list(params, "experience", settings.experience)
    _add_list(params, "degree", settings.degree)
    _add_list(params, "scale", settings.scale)
    _add_list(params, "industry", settings.industry)
    _add_list(params, "stage", settings.stage_codes)
    base = "https://www.zhipin.com/web/geek/jobs"
    if not params:
        return base
    return base + "?" + "&".join(params)


def screen_file_name(stamp: str, job_type: str, keyword: str) -> str:
    return f"{stamp}_{slug(job_type)}_{slug(keyword)}.jsonl"


def _strings(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return [str(item).strip() for item in value if str(item).strip()]


def _code(codes: dict, kind: str, name: str) -> str:
    table = codes.get(kind) if isinstance(codes, dict) else None
    if not isinstance(table, dict) or not table:
        raise SystemExit(f"boss.yaml 的 codes.{kind} 没有表")
    code = table.get(name)
    if isinstance(code, str) and code.strip():
        return code.strip()
    for existing in table.values():
        if name == str(existing):
            return name
    raise SystemExit(f"boss.yaml 的 {kind} 无法对应 Boss 选项: {name}")


def _codes(codes: dict, kind: str, values) -> list[str]:
    names = _strings(values)
    if not names:
        return []
    return [_code(codes, kind, name) for name in names]


def _add(params: list[str], name: str, value: str | None) -> None:
    if value and value != UNLIMITED:
        params.append(f"{name}={value}")


def _add_list(params: list[str], name: str, values: list[str]) -> None:
    if not values or UNLIMITED in values:
        return
    params.append(name + "=" + ",".join(values))


def _wait_time(raw) -> int:
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return 18
    if parsed <= 0:
        return 18
    return max(18, parsed)
