"""列表 JSON 与 DOM 卡片解析，提取列表与详情接口的全部岗位事实。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from boss_screen.rules import classify_city, is_search_city, join_area


@dataclass
class Card:
    encrypt_id: str = ""
    job: str = ""
    company: str = ""
    salary: str = ""
    area: str = ""
    href: str = ""
    tags: str = ""
    recruiter: str = ""
    recruiter_title: str = ""
    degree: str = ""
    experience: str = ""
    industry: str = ""
    scale: str = ""
    financing: str = ""


def overlay(base: Card, extra: Card) -> Card:
    area = base.area
    if classify_city(base.area) == "其它" and is_search_city(classify_city(extra.area)):
        area = extra.area
    elif not area:
        area = extra.area
    return Card(
        encrypt_id=_first(base.encrypt_id, extra.encrypt_id),
        job=_first(base.job, extra.job),
        company=_first(base.company, extra.company),
        salary=_first(base.salary, extra.salary),
        area=area,
        href=_first(base.href, extra.href),
        tags=_first(base.tags, extra.tags),
        recruiter=_first(base.recruiter, extra.recruiter),
        recruiter_title=_first(base.recruiter_title, extra.recruiter_title),
        degree=_first(base.degree, extra.degree),
        experience=_first(base.experience, extra.experience),
        industry=_first(base.industry, extra.industry),
        scale=_first(base.scale, extra.scale),
        financing=_first(base.financing, extra.financing),
    )


def ingest_job_list(body: str) -> list[Card]:
    try:
        root = json.loads(body)
    except json.JSONDecodeError:
        return []
    if not isinstance(root, dict):
        return []
    zp = _as_dict(root.get("zpData"))
    listing = zp.get("jobList") or zp.get("list") or root.get("jobList")
    if not isinstance(listing, list):
        return []
    cards: list[Card] = []
    for item in listing:
        if not isinstance(item, dict):
            continue
        card = _card_from_item(item)
        if card is not None:
            cards.append(card)
    return cards


def _card_from_item(job: dict) -> Card | None:
    job_info = _as_dict(job.get("jobInfo"))
    boss = _as_dict(job.get("bossInfo"))
    brand_raw = job.get("brandComInfo")
    if not isinstance(brand_raw, dict):
        brand_raw = job.get("brand")
    brand = brand_raw if isinstance(brand_raw, dict) else {}
    encrypt_id = _first(_text(job, "encryptId"), _text(job, "encryptJobId"), _text(job_info, "encryptId"))
    if not encrypt_id:
        return None
    job_name = _first(_text(job, "jobName"), _text(job_info, "jobName"))
    company = _first(_text(job, "brandName"), _text(brand, "brandName"), _text(job, "companyName"))
    if not job_name and not company:
        return None
    city = _first(_text(job, "cityName"), _text(job_info, "locationName"), _text(job, "city"))
    district = _first(_text(job, "areaDistrict"), _text(job, "district"))
    area = join_area(city, district, _text(job, "businessDistrict"))
    salary = _first(_text(job, "salaryDesc"), _text(job_info, "salaryDesc"))
    tags = _labels(job, "skills", "jobLabels") or _labels(job_info, "skills", "jobLabels")
    recruiter = _first(_text(job, "bossName"), _text(boss, "name"))
    recruiter_title = _first(_text(job, "bossTitle"), _text(boss, "title"), _text(job, "bossJobName"))
    degree = _first(_text(job, "jobDegree"), _text(job, "degreeName"), _text(job_info, "degreeName"))
    experience = _first(_text(job, "jobExperience"), _text(job, "experienceName"), _text(job_info, "experienceName"))
    industry = _first(
        _text(job, "brandIndustry"),
        _text(brand, "industryName"),
        _text(brand, "brandIndustryName"),
        _text(job_info, "industryName"),
    )
    scale = _first(
        _text(job, "brandScaleName"),
        _text(brand, "scaleName"),
        _text(brand, "brandScaleName"),
        _text(job_info, "scaleName"),
    )
    financing = _first(
        _text(job, "brandStageName"),
        _text(brand, "stageName"),
        _text(brand, "brandStageName"),
        _text(job_info, "stageName"),
    )
    return Card(
        encrypt_id=encrypt_id,
        job=job_name,
        company=company,
        salary=salary,
        area=area,
        href=f"/job_detail/{encrypt_id}.html",
        tags=tags,
        recruiter=recruiter,
        recruiter_title=recruiter_title,
        degree=degree,
        experience=experience,
        industry=industry,
        scale=scale,
        financing=financing,
    )


def parse_detail(body: str) -> dict:
    try:
        root = json.loads(body)
    except json.JSONDecodeError:
        return {}
    zp = _as_dict(root.get("zpData")) if isinstance(root, dict) else {}
    job_info = _as_dict(zp.get("jobInfo"))
    boss = _as_dict(zp.get("bossInfo"))
    brand = _as_dict(zp.get("brandComInfo"))
    city = _text(job_info, "locationName")
    district = _first(
        _text(job_info, "areaDistrict"),
        _text(job_info, "districtName"),
        _text(job_info, "district"),
    )
    area = join_area(city, district, _text(job_info, "businessDistrict")) or city
    industry = _first(_text(brand, "industryName"), _text(brand, "brandIndustryName"), _text(job_info, "industryName"))
    scale = _first(_text(brand, "scaleName"), _text(brand, "brandScaleName"), _text(job_info, "scaleName"))
    financing = _first(_text(brand, "stageName"), _text(brand, "brandStageName"), _text(job_info, "stageName"))
    return {
        "job": _text(job_info, "jobName"),
        "salary": _text(job_info, "salaryDesc"),
        "area": area,
        "company": _text(brand, "brandName"),
        "recruiter": _text(boss, "name"),
        "recruiterTitle": _text(boss, "title"),
        "active": _active(boss),
        "jd": _text(job_info, "postDescription"),
        "degree": _text(job_info, "degreeName"),
        "experience": _text(job_info, "experienceName"),
        "industry": industry,
        "scale": scale,
        "financing": financing,
    }


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _active(obj: object) -> str:
    value = obj.get("activeTimeDesc") if isinstance(obj, dict) else None
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or text.lower() in ("true", "false"):
        return ""
    return text


def _text(obj: object, key: str) -> str:
    if not isinstance(obj, dict):
        return ""
    value = obj.get(key)
    return value.strip() if isinstance(value, str) else ""


def _first(*parts: str) -> str:
    for part in parts:
        if part and part.strip():
            return part.strip()
    return ""


def _labels(obj: object, *keys: str) -> str:
    parts: list[str] = []
    for key in keys:
        _collect(obj.get(key) if isinstance(obj, dict) else None, parts)
    return "、".join(parts)


def _collect(value, parts: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            _collect(item, parts)
        return
    if isinstance(value, dict):
        text = _first(_text(value, "name"), _text(value, "label"), _text(value, "skillName"))
        if text and text not in parts:
            parts.append(text)
        return
    if isinstance(value, str):
        text = value.strip()
        if text and text not in parts:
            parts.append(text)
