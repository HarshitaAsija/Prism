"""Canonical skill matching; resume mentions are supporting claims, not verification."""

import re
from config import SKILL_CREDIBILITY

ALIASES = {
    "js": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "golang": "go",
    "go": "go",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "reactjs": "react",
    "react.js": "react",
    "react": "react",
    "nodejs": "node.js",
    "node.js": "node.js",
    "k8s": "kubernetes",
    "kubernetes": "kubernetes",
    "amazon web services": "aws",
    "aws": "aws",
    "py": "python",
    "python": "python",
    "c sharp": "c#",
    "c#": "c#",
    "cpp": "c++",
    "c++": "c++",
}


def canonical(skill):
    value = re.sub(r"\s+", " ", str(skill).strip().lower())
    return ALIASES.get(value, value)


def mentions(skill, text):
    names = {skill, *[name for name, target in ALIASES.items() if target == skill]}
    return any(
        re.search(r"(?<![\w+#])" + re.escape(name) + r"(?![\w+#])", text.lower()) for name in names
    )


def skill_score(candidate, jd_parsed):
    listed = candidate.get("skills") or []
    if isinstance(listed, str):
        listed = re.split("[;,]", listed)
    listed = {canonical(s.get("name", "") if isinstance(s, dict) else s) for s in listed}
    # Count each distinct role only once. Duplicated descriptions add no evidence.
    descriptions = {
        str(j.get("description") or "").strip().lower()
        for j in (candidate.get("career_history") or [])
        if isinstance(j, dict)
    }
    rows = []
    weighted = 0.0
    total = 0.0
    seen = set()
    for required, key, weight in [(True, "required_skills", 1.0), (False, "preferred_skills", 0.4)]:
        for raw in jd_parsed.get(key) or []:
            skill = canonical(raw)
            if not skill or skill in seen:
                continue
            seen.add(skill)
            evidence = sum(bool(desc) and mentions(skill, desc) for desc in descriptions)
            matched = skill in listed or evidence > 0
            credibility = SKILL_CREDIBILITY[
                "multi_project" if evidence > 1 else "one_project" if evidence else "no_evidence"
            ]
            weighted += weight * float(matched) * credibility
            total += weight
            rows.append(
                {
                    "skill": skill,
                    "required": required,
                    "match_level": float(matched),
                    "evidence": evidence,
                    "credibility": credibility,
                    "status": "full" if matched else "missing",
                }
            )
    return (round(min(1.0, weighted / total), 4) if total else 0.5), rows
