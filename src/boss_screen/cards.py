"""列表 JSON 与 DOM 卡片。只吃 Boss 已经返回的字段。"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from boss_screen.rules import classify_city, is_search_city, join_area


@dataclass
class Card:
    job: str = ""
    company: str = ""
    area: str = ""
    active: str = ""
    href: str = ""
    encrypt_id: str = ""
    tags: str = ""
    recruiter: str = ""

    def with_active(self, active: str) -> Card:
        return replace(self, active=active)


def overlay(base: Card, extra: Card) -> Card:
    area = base.area
    if classify_city(base.area) == "其它" and is_search_city(classify_city(extra.area)):
        area = extra.area
    return Card(
        job=base.job,
        company=base.company,
        area=area,
        active=_first(base.active, extra.active),
        href=_first(base.href, extra.href),
        encrypt_id=_first(base.encrypt_id, extra.encrypt_id),
        tags=_first(base.tags, extra.tags),
        recruiter=_first(base.recruiter, extra.recruiter),
    )


def ingest_job_list(body: str) -> list[Card]:
    try:
        root = json.loads(body)
    except json.JSONDecodeError:
        return []
    if not isinstance(root, dict):
        return []
    zp = root.get("zpData") if isinstance(root.get("zpData"), dict) else {}
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
    job_info = job.get("jobInfo") if isinstance(job.get("jobInfo"), dict) else {}
    boss = job.get("bossInfo") if isinstance(job.get("bossInfo"), dict) else {}
    brand = job.get("brandComInfo") if isinstance(job.get("brandComInfo"), dict) else None
    if brand is None and isinstance(job.get("brand"), dict):
        brand = job["brand"]
    brand = brand or {}
    encrypt_id = _first(_text(job, "encryptId"), _text(job, "encryptJobId"), _text(job_info, "encryptId"))
    if not encrypt_id:
        return None
    active = _active(job) or _active(boss)
    job_name = _first(_text(job, "jobName"), _text(job_info, "jobName"))
    company = _first(_text(job, "brandName"), _text(brand, "brandName"), _text(job, "companyName"))
    if not job_name and not company:
        return None
    city = _first(_text(job, "cityName"), _text(job_info, "locationName"), _text(job, "city"))
    district = _first(_text(job, "areaDistrict"), _text(job, "district"))
    area = join_area(city, district, _text(job, "businessDistrict"))
    tags = _labels(job, "skills", "jobLabels") or _labels(job_info, "skills", "jobLabels")
    recruiter = _first(_text(job, "bossTitle"), _text(boss, "title"), _text(job, "bossJobName"))
    return Card(
        job=job_name,
        company=company,
        area=area,
        active=active,
        href=f"/job_detail/{encrypt_id}.html",
        encrypt_id=encrypt_id,
        tags=tags,
        recruiter=recruiter,
    )


def parse_detail(body: str) -> dict:
    try:
        root = json.loads(body)
    except json.JSONDecodeError:
        return {}
    zp = root.get("zpData") if isinstance(root, dict) and isinstance(root.get("zpData"), dict) else {}
    job_info = zp.get("jobInfo") if isinstance(zp.get("jobInfo"), dict) else {}
    boss = zp.get("bossInfo") if isinstance(zp.get("bossInfo"), dict) else {}
    brand = zp.get("brandComInfo") if isinstance(zp.get("brandComInfo"), dict) else {}
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


def _active(obj: dict) -> str:
    value = obj.get("activeTimeDesc") if isinstance(obj, dict) else None
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or text.lower() in ("true", "false"):
        return ""
    return text


def _text(obj: dict, key: str) -> str:
    if not isinstance(obj, dict):
        return ""
    value = obj.get(key)
    return value.strip() if isinstance(value, str) else ""


def _first(*parts: str) -> str:
    for part in parts:
        if part and part.strip():
            return part.strip()
    return ""


def _labels(obj: dict, *keys: str) -> str:
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
