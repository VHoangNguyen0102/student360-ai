"""Scholarship tools: fuzzy lookup and scholarship details."""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import date, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.database import get_pool

logger = structlog.get_logger()


def _uid(config: RunnableConfig) -> str:
	return config["configurable"]["user_id"]


def _serialize(value: Any) -> Any:
	"""Recursively make asyncpg data JSON-serializable."""
	if isinstance(value, Decimal):
		return float(value)
	if isinstance(value, uuid.UUID):
		return str(value)
	if isinstance(value, (datetime, date)):
		return value.isoformat()
	if isinstance(value, dict):
		return {k: _serialize(v) for k, v in value.items()}
	if isinstance(value, (list, tuple)):
		return [_serialize(v) for v in value]
	return value


def _ensure_uuid_list(value: Any) -> list[str]:
	if value is None:
		return []
	if isinstance(value, list):
		return [str(item) for item in value if str(item).strip()]
	if isinstance(value, tuple):
		return [str(item) for item in value if str(item).strip()]
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
			if isinstance(parsed, list):
				return [str(item) for item in parsed if str(item).strip()]
		except json.JSONDecodeError:
			pass
		return [item.strip() for item in value.split(",") if item.strip()]
	return []


_VIETNAMESE_COUNT_WORDS = {
	"mot": 1,
	"một": 1,
	"hai": 2,
	"ba": 3,
	"bon": 4,
	"bốn": 4,
	"tu": 4,
	"tư": 4,
	"nam": 5,
	"năm": 5,
	"sau": 6,
	"sáu": 6,
	"bay": 7,
	"bảy": 7,
	"tam": 8,
	"tám": 8,
}


def _normalize_text_for_count(text: str) -> str:
	normalized = unicodedata.normalize("NFD", text.lower())
	return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _extract_requested_recommendation_count(user_query: str) -> int | None:
	"""Infer an explicit requested recommendation count from a chat query."""
	normalized = _normalize_text_for_count(user_query or "")
	if not normalized.strip():
		return None

	# "mot so hoc bong" / "1 so hoc bong" means "some scholarships", not exactly one.
	without_some_phrase = re.sub(r"\b(?:mot|1)\s+so\b", " ", normalized)
	patterns = [
		r"\b(?:top|lay|chon|goi y|de xuat|tim|cho toi|cho minh)\s+(\d{1,2})\b",
		r"\b(\d{1,2})\s+(?:hoc bong|suat|recommendation|recommendations|ket qua)\b",
	]
	for pattern in patterns:
		match = re.search(pattern, without_some_phrase)
		if match:
			return int(match.group(1))

	for word, value in _VIETNAMESE_COUNT_WORDS.items():
		if re.search(rf"\b{re.escape(word)}\s+(?:hoc bong|suat|ket qua)\b", without_some_phrase):
			return value

	return None


def _build_scholarship_detail_response(
	scholarship_data: dict[str, Any],
	requirement_items: list[dict[str, Any]],
	document_items: list[dict[str, Any]],
	now: datetime,
	include_warnings: bool = False,
) -> dict[str, Any]:
	deadline = scholarship_data.get("application_deadline")
	is_open_for_application = bool(
		scholarship_data.get("is_active")
		and (deadline is None or deadline >= now)
	)

	required_requirement_count = sum(1 for item in requirement_items if item.get("is_required"))
	required_document_count = sum(1 for item in document_items if item.get("is_required"))

	response = {
		"scholarship": _serialize(scholarship_data),
		"conditions": {
			"eligibility_criteria": _serialize(scholarship_data.get("eligibility_criteria")),
			"benefits": _serialize(scholarship_data.get("benefits")),
			"is_active": _serialize(scholarship_data.get("is_active")),
			"application_deadline": _serialize(deadline),
			"result_announcement_date": _serialize(scholarship_data.get("result_announcement_date")),
			"is_open_for_application": is_open_for_application,
		},
		"requirements": {
			"total": len(requirement_items),
			"required_count": required_requirement_count,
			"items": _serialize(requirement_items),
		},
		"documents": {
			"total": len(document_items),
			"required_count": required_document_count,
			"items": _serialize(document_items),
		},
		"checklist_summary": {
			"must_satisfy_requirements": required_requirement_count,
			"must_submit_documents": required_document_count,
		},
	}

	if include_warnings:
		if not requirement_items:
			response["warning_requirements"] = "Học bổng chưa có requirement checklist."
		if not document_items:
			response["warning_documents"] = "Học bổng chưa có document checklist."

	return response


def _normalize_text(text: str) -> str:
	"""Normalize text to improve matching tolerance (accent/case/punctuation-insensitive)."""
	if not text:
		return ""
	text = unicodedata.normalize("NFKD", text)
	text = "".join(char for char in text if not unicodedata.combining(char))
	text = text.lower()
	text = re.sub(r"[^a-z0-9\s]", " ", text)
	text = re.sub(r"\s+", " ", text).strip()
	return text


def _tokenize(text: str) -> list[str]:
	normalized = _normalize_text(text)
	if not normalized:
		return []
	return [token for token in normalized.split(" ") if token]


def _char_ngrams(text: str, n: int = 2) -> set[str]:
	compact = _normalize_text(text).replace(" ", "")
	if not compact:
		return set()
	if len(compact) < n:
		return {compact}
	return {compact[i : i + n] for i in range(len(compact) - n + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
	if not left and not right:
		return 1.0
	if not left or not right:
		return 0.0
	inter = len(left & right)
	union = len(left | right)
	return inter / union if union else 0.0


def _score_name_match(query: str, row: dict[str, Any]) -> float:
	"""Compute fuzzy score in [0,1] for one scholarship candidate."""
	query_norm = _normalize_text(query)
	name = str(row.get("name") or "")
	provider = str(row.get("provider") or "")
	category = str(row.get("category_name") or "")
	target_norm = _normalize_text(name)
	context_norm = _normalize_text(" ".join(part for part in [name, provider, category] if part))

	if not query_norm or not target_norm:
		return 0.0

	if query_norm == target_norm:
		return 1.0

	sequence_score = SequenceMatcher(None, query_norm, target_norm).ratio()
	containment_score = 0.0
	if query_norm in target_norm:
		containment_score = min(1.0, len(query_norm) / max(len(target_norm), 1) + 0.2)
	elif target_norm in query_norm:
		containment_score = min(1.0, len(target_norm) / max(len(query_norm), 1) + 0.1)

	query_tokens = set(_tokenize(query_norm))
	context_tokens = set(_tokenize(context_norm))
	token_score = _jaccard(query_tokens, context_tokens)

	bigram_score = _jaccard(_char_ngrams(query_norm, n=2), _char_ngrams(target_norm, n=2))
	prefix_bonus = 1.0 if target_norm.startswith(query_norm) else 0.0

	base = max(sequence_score, containment_score)
	score = 0.48 * base + 0.27 * token_score + 0.2 * bigram_score + 0.05 * prefix_bonus
	return round(max(0.0, min(score, 1.0)), 6)


async def _query_scholarship_candidates(name_query: str, active_only: bool) -> list[dict[str, Any]]:
	"""Two-pass candidate retrieval: targeted search first, then broader fallback."""
	tokens = _tokenize(name_query)
	like_pattern = f"%{name_query.strip()}%" if name_query.strip() else "%"
	print(
		f"[scholarship-search] like={like_pattern!r} tokens={tokens} active_only={active_only}",
		flush=True,
	)
	pool = await get_pool()
	print("[scholarship-search] db_pool_ready=True", flush=True)
	async with pool.acquire() as conn:
		targeted_rows = await conn.fetch(
			"""
			SELECT s.id,
				   s.name,
				   s.provider,
				   s.is_active,
				   s.application_deadline,
				   s.result_announcement_date,
				   s.updated_at,
				   sc.name AS category_name
			FROM scholarships s
			LEFT JOIN scholarship_categories sc ON sc.id = s.category_id
			WHERE ($1::boolean = false OR s.is_active = true)
			  AND (
					s.name ILIKE $2
				 OR EXISTS (
						SELECT 1
						FROM unnest($3::text[]) AS token
						WHERE s.name ILIKE '%' || token || '%'
					)
			  )
			ORDER BY s.updated_at DESC NULLS LAST
			LIMIT 300
			""",
			active_only,
			like_pattern,
			tokens,
		)
		print(f"[scholarship-search] targeted_rows={len(targeted_rows)}", flush=True)

		if len(targeted_rows) >= 10:
			return [dict(row) for row in targeted_rows]

		fallback_rows = await conn.fetch(
			"""
			SELECT s.id,
				   s.name,
				   s.provider,
				   s.is_active,
				   s.application_deadline,
				   s.result_announcement_date,
				   s.updated_at,
				   sc.name AS category_name
			FROM scholarships s
			LEFT JOIN scholarship_categories sc ON sc.id = s.category_id
			WHERE ($1::boolean = false OR s.is_active = true)
			ORDER BY s.updated_at DESC NULLS LAST
			LIMIT 120
			""",
			active_only,
		)
		print(f"[scholarship-search] fallback_rows={len(fallback_rows)}", flush=True)
		return [dict(row) for row in fallback_rows]


@tool
async def find_scholarship_id_by_name(
	scholarship_name: str,
	max_results: int = 5,
	active_only: bool = False,
) -> str:
	"""
	Find scholarship id by name with typo-tolerant fuzzy matching.

	Args:
		scholarship_name: Free-text scholarship name to search.
		max_results: Number of candidates to return (1-10).
		active_only: If true, only search scholarships with is_active = true.

	Returns:
		JSON string with best_match and ranked candidates.
	"""
	query = (scholarship_name or "").strip()
	logger.info("find_scholarship_id_by_name_started", query=query)
	print(
		f"[scholarship-search] started query={query!r} active_only={active_only} max_results={max_results}",
		flush=True,
	)
	if not query:
		return json.dumps(
			{
				"error": "scholarship_name is required.",
				"hint": "Ví dụ: 'FPT University Merit Scholarship 2026'",
			},
			ensure_ascii=False,
		)

	safe_limit = max(1, min(int(max_results), 10))

	try:
		rows = await _query_scholarship_candidates(query, active_only=active_only)
		logger.info("find_scholarship_id_by_name_executed", query=query, candidate_count=len(rows))
		print(f"[scholarship-search] query_completed candidate_count={len(rows)}", flush=True)
		if not rows:
			return json.dumps(
				{
					"query": query,
					"best_match": None,
					"candidates": [],
					"message": "Không tìm thấy học bổng nào trong hệ thống.",
				},
				ensure_ascii=False,
			)

		ranked: list[dict[str, Any]] = []
		for row in rows:
			score = _score_name_match(query, row)
			ranked.append(
				{
					"id": row.get("id"),
					"name": row.get("name"),
					"provider": row.get("provider"),
					"category": row.get("category_name"),
					"is_active": row.get("is_active"),
					"application_deadline": row.get("application_deadline"),
					"result_announcement_date": row.get("result_announcement_date"),
					"score": score,
				}
			)

		ranked.sort(
			key=lambda item: (
				item["score"],
				bool(item.get("is_active")),
				str(item.get("name") or "").lower(),
			),
			reverse=True,
		)

		top = ranked[:safe_limit]
		best = top[0] if top else None
		confidence = "high" if best and best["score"] >= 0.85 else "medium" if best and best["score"] >= 0.6 else "low"

		payload = {
			"query": query,
			"search_mode": {
				"accent_insensitive": True,
				"typo_tolerant": True,
				"active_only": active_only,
			},
			"best_match": _serialize(best) if best else None,
			"best_match_id": _serialize(best.get("id")) if best else None,
			"confidence": confidence,
			"candidates": _serialize(top),
		}

		if best and best["score"] < 0.5:
			payload["warning"] = (
				"Kết quả khớp thấp. Nên xác nhận lại tên học bổng hoặc lấy từ danh sách candidates."
			)

		return json.dumps(payload, ensure_ascii=False)
	except Exception as exc:  # pragma: no cover - defensive fallback for tool runtime
		logger.exception("find_scholarship_id_by_name_failed", query=query)
		print(f"[scholarship-search] failed query={query!r} error={exc!r}", flush=True)
		return json.dumps(
			{
				"error": f"KHÔNG TÌM THẤY HỌC BỔNG TRONG HỆ THỐNG!",
				"query": query,
			},
			ensure_ascii=False,
		)


@tool
async def get_scholarship_details(scholarship_id: str) -> str:
	"""
	Return full scholarship details by id, including conditions, requirements, and required documents.

	Args:
		scholarship_id: UUID of scholarship.

	Returns:
		JSON string with all key data needed to clarify eligibility and submission requirements.
	"""
	raw_id = (scholarship_id or "").strip()
	if not raw_id:
		return json.dumps({"error": "scholarship_id is required."}, ensure_ascii=False)

	try:
		scholarship_uuid = str(uuid.UUID(raw_id))
	except ValueError:
		return json.dumps(
			{
				"error": "scholarship_id must be a valid UUID.",
				"scholarship_id": raw_id,
			},
			ensure_ascii=False,
		)

	try:
		pool = await get_pool()
		async with pool.acquire() as conn:
			scholarship = await conn.fetchrow(
				"""
				SELECT s.id,
					   s.name,
					   s.description,
					   s.eligibility_criteria,
					   s.benefits,
					   s.amount,
					   s.currency,
					   s.quantity,
					   s.application_deadline,
					   s.result_announcement_date,
					   s.provider,
					   s.provider_id,
					   s.contact_email,
					   s.contact_phone,
					   s.official_website,
					   s.image,
					   s.category_id,
					   s.is_active,
					   s.created_at,
					   s.updated_at,
					   sc.name AS category_name,
					   sc.description AS category_description
				FROM scholarships s
				LEFT JOIN scholarship_categories sc ON sc.id = s.category_id
				WHERE s.id = $1
				LIMIT 1
				""",
				scholarship_uuid,
			)

			if scholarship is None:
				return json.dumps(
					{
						"error": "Scholarship not found.",
						"scholarship_id": scholarship_uuid,
					},
					ensure_ascii=False,
				)

			requirements = await conn.fetch(
				"""
				SELECT id,
					   scholarship_id,
					   title,
					   description,
					   is_required,
					   sort_order,
					   created_at,
					   updated_at
				FROM scholarship_requirements
				WHERE scholarship_id = $1
				ORDER BY sort_order ASC, created_at ASC
				""",
				scholarship_uuid,
			)

			documents = await conn.fetch(
				"""
				SELECT id,
					   scholarship_id,
					   document_name,
					   document_type,
					   is_required,
					   max_file_size_mb,
					   sample_url,
					   created_at,
					   updated_at
				FROM scholarship_documents
				WHERE scholarship_id = $1
				ORDER BY is_required DESC, created_at ASC
				""",
				scholarship_uuid,
			)

		scholarship_data = dict(scholarship)
		requirement_items = [dict(item) for item in requirements]
		document_items = [dict(item) for item in documents]

		response = _build_scholarship_detail_response(
			scholarship_data,
			requirement_items,
			document_items,
			datetime.utcnow(),
			include_warnings=True,
		)

		return json.dumps(response, ensure_ascii=False)

	except Exception as exc:  # pragma: no cover - defensive fallback for tool runtime
		logger.error("get_scholarship_details_failed", error=str(exc), scholarship_id=raw_id)
		return json.dumps(
			{
				"error": f"Lỗi lấy chi tiết học bổng: {str(exc)}",
				"scholarship_id": raw_id,
			},
			ensure_ascii=False,
		)


@tool
async def get_all_scholarships(
	active_only: bool = True,
	open_only: bool = False,
	limit: int = 200,
	offset: int = 0,
) -> str:
	"""
	Lấy danh sách học bổng với filter cơ bản (active/open) và phân trang.

	Args:
		active_only: Nếu true, chỉ lấy học bổng is_active = true.
		open_only: Nếu true, chỉ lấy học bổng còn hạn nộp (deadline >= hiện tại).
		limit: Số bản ghi trả về (1-500).
		offset: Vị trí bắt đầu (>= 0).

	Returns:
		JSON string chứa danh sách học bổng và thông tin phân trang.
	"""
	safe_limit = max(1, min(int(limit), 500))
	safe_offset = max(0, int(offset))

	try:
		now = datetime.utcnow()
		pool = await get_pool()
		async with pool.acquire() as conn:
			rows = await conn.fetch(
				"""
				SELECT s.id,
				       s.name,
				       s.description,
				       s.eligibility_criteria,
				       s.benefits,
				       s.provider,
				       s.is_active,
				       s.application_deadline,
				       s.result_announcement_date,
				       s.updated_at,
				       sc.name AS category_name
				FROM scholarships s
				LEFT JOIN scholarship_categories sc ON sc.id = s.category_id
				WHERE ($1::boolean = false OR s.is_active = true)
				  AND ($2::boolean = false OR (s.is_active = true AND (s.application_deadline IS NULL OR s.application_deadline >= $3)))
				ORDER BY s.updated_at DESC NULLS LAST
				LIMIT $4 OFFSET $5
				""",
				active_only,
				open_only,
				now,
				safe_limit,
				safe_offset,
			)

			scholarship_ids = [row["id"] for row in rows if row.get("id")]
			requirement_items_map: dict[str, list[dict[str, Any]]] = {}
			document_items_map: dict[str, list[dict[str, Any]]] = {}
			if scholarship_ids:
				requirement_rows = await conn.fetch(
					"""
					SELECT id,
					       scholarship_id,
					       title,
					       description,
					       is_required,
					       sort_order,
					       created_at,
					       updated_at
					FROM scholarship_requirements
					WHERE scholarship_id = ANY($1::uuid[])
					ORDER BY sort_order ASC, created_at ASC
					""",
					scholarship_ids,
				)
				for row in requirement_rows:
					item = dict(row)
					sid = str(item.get("scholarship_id"))
					requirement_items_map.setdefault(sid, []).append(item)

				document_rows = await conn.fetch(
					"""
					SELECT id,
					       scholarship_id,
					       document_name,
					       document_type,
					       is_required,
					       max_file_size_mb,
					       sample_url,
					       created_at,
					       updated_at
					FROM scholarship_documents
					WHERE scholarship_id = ANY($1::uuid[])
					ORDER BY is_required DESC, created_at ASC
					""",
					scholarship_ids,
				)
				for row in document_rows:
					item = dict(row)
					sid = str(item.get("scholarship_id"))
					document_items_map.setdefault(sid, []).append(item)

		items = []
		for row in rows:
			row_dict = dict(row)
			sid = str(row_dict.get("id"))
			requirement_items = requirement_items_map.get(sid, [])
			document_items = document_items_map.get(sid, [])
			items.append(
				_build_scholarship_detail_response(
					row_dict,
					requirement_items,
					document_items,
					now,
					include_warnings=True,
				)
			)

		payload = {
			"filters": {
				"active_only": active_only,
				"open_only": open_only,
			},
			"paging": {
				"limit": safe_limit,
				"offset": safe_offset,
				"returned": len(items),
			},
			"items": _serialize(items),
		}

		return json.dumps(payload, ensure_ascii=False)
	except Exception as exc:  # pragma: no cover - defensive fallback for tool runtime
		logger.exception("get_all_scholarships_failed", error=str(exc))
		return json.dumps(
			{
				"error": f"Lỗi lấy danh sách học bổng: {str(exc)}",
			},
			ensure_ascii=False,
		)

def _build_profile_text(profile: dict[str, Any]) -> str:
    """Flatten profile fields to a single text blob for fuzzy matching."""
    fields = [
        "major",
        "university",
        "school",
        "faculty",
        "program",
        "skills",
        "interests",
        "keywords",
        "career_goal",
        "location",
        "country",
    ]
    parts: list[str] = []
    for field in fields:
        value = profile.get(field)
        if isinstance(value, str) and value.strip():
            parts.append(value)
        elif isinstance(value, (list, tuple)):
            parts.extend(str(item) for item in value if str(item).strip())
    return " ".join(parts)


def _score_profile_match(profile: dict[str, Any], row: dict[str, Any]) -> tuple[float, list[str]]:
    """Score scholarship against profile using token overlap and fuzzy similarity."""
    profile_text = _build_profile_text(profile)
    profile_tokens = set(_tokenize(profile_text))

    scholarship_text = " ".join(
        str(row.get(field) or "")
        for field in [
            "name",
            "description",
            "eligibility_criteria",
            "benefits",
            "provider",
            "category_name",
        ]
    )
    scholarship_tokens = set(_tokenize(scholarship_text))

    if not profile_tokens or not scholarship_tokens:
        return 0.0, []

    token_score = _jaccard(profile_tokens, scholarship_tokens)
    bigram_score = _jaccard(_char_ngrams(profile_text, n=2), _char_ngrams(scholarship_text, n=2))
    name_score = SequenceMatcher(
        None,
        _normalize_text(profile_text),
        _normalize_text(str(row.get("name") or "")),
    ).ratio()

    score = 0.5 * token_score + 0.3 * bigram_score + 0.2 * name_score
    matched_terms = sorted(profile_tokens & scholarship_tokens)[:15]
    return round(max(0.0, min(score, 1.0)), 6), matched_terms


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
        return [item.strip() for item in re.split(r"[,;\n]", stripped) if item.strip()]
    return []


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (list, tuple, dict)):
            text = str(value).strip()
            if text:
                return text
    return None


def _shorten(text: str | None, limit: int = 120) -> str | None:
    if not text:
        return None
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _extract_query_profile(user_query: str) -> dict[str, Any]:
    text = user_query or ""
    profile: dict[str, Any] = {}
    gpa_match = re.search(r"\bgpa\s*(?:>=|>|:|is|la|là)?\s*([0-9]+(?:[.,][0-9]+)?)", text, re.I)
    if gpa_match:
        try:
            profile["gpa"] = float(gpa_match.group(1).replace(",", "."))
        except ValueError:
            pass

    major_patterns = [
        r"\b(computer science|software engineering|information technology|data science|artificial intelligence|ai|stem)\b",
        r"\b(khoa hoc may tinh|khoa học máy tính|cong nghe thong tin|công nghệ thông tin)\b",
    ]
    majors: list[str] = []
    for pattern in major_patterns:
        majors.extend(match.group(1) for match in re.finditer(pattern, text, re.I))
    if majors:
        profile["major"] = " ".join(dict.fromkeys(majors))

    field_patterns = {
        "major": r"(?:ngành|major)\s+(.+?)(?=\s+(?:khoa|trường|university|school|gpa|yêu cầu|yeu cau)\b|[,.;]|$)",
        "faculty": r"(?:khoa|faculty)\s+(.+?)(?=\s+(?:ngành|major|trường|university|school|gpa|yêu cầu|yeu cau)\b|[,.;]|$)",
        "university": r"(?:trường|university|school)\s+(.+?)(?=\s+(?:ngành|major|khoa|faculty|gpa|yêu cầu|yeu cau)\b|[,.;]|$)",
    }
    for key, pattern in field_patterns.items():
        match = re.search(pattern, text, re.I)
        if match:
            profile[key] = match.group(1).strip()
    return profile


def _build_profile_summary(profile_payload: dict[str, Any], user_query: str) -> dict[str, Any]:
    academics = profile_payload.get("academics") if isinstance(profile_payload.get("academics"), list) else []
    latest_academic = academics[0] if academics and isinstance(academics[0], dict) else {}
    skills = profile_payload.get("skills") if isinstance(profile_payload.get("skills"), list) else []
    interests = profile_payload.get("interests") if isinstance(profile_payload.get("interests"), list) else []
    user = profile_payload.get("user") if isinstance(profile_payload.get("user"), dict) else {}
    query_profile = _extract_query_profile(user_query)

    summary = {
        "major": query_profile.get("major") or latest_academic.get("major"),
        "university": latest_academic.get("university"),
        "faculty": latest_academic.get("faculty"),
        "program": latest_academic.get("education_program"),
        "degree_level": latest_academic.get("degree_level"),
        "current_year": latest_academic.get("current_year"),
        "gpa": query_profile.get("gpa") or latest_academic.get("gpa"),
        "skills": [item.get("name") for item in skills if isinstance(item, dict) and item.get("name")],
        "interests": [item.get("name") for item in interests if isinstance(item, dict) and item.get("name")],
        "career_goal": user.get("career_goal"),
        "country": user.get("country"),
        "keywords": user_query,
    }
    return {key: value for key, value in summary.items() if value not in (None, "", [])}


def _format_profile_field(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _build_recommendation_reply_hint(profile: dict[str, Any], has_items: bool) -> str:
    if not has_items:
        return "Tôi chưa tìm thấy học bổng phù hợp từ dữ liệu hiện tại."

    details: list[str] = []
    major = _format_profile_field(profile.get("major"))
    faculty = _format_profile_field(profile.get("faculty"))
    university = _format_profile_field(profile.get("university"))
    gpa = _format_profile_field(profile.get("gpa"))

    if major:
        details.append(f"ngành {major}")
    if faculty:
        details.append(f"khoa {faculty}")
    if university:
        details.append(f"trường {university}")
    if gpa:
        details.append(f"GPA {gpa}")

    if details:
        return (
            f"Dựa trên profile của bạn ({', '.join(details)}), "
            "tôi đề xuất các học bổng phù hợp dưới đây. Nhấn vào từng thẻ để xem tóm tắt."
        )

    return "Tôi đã tìm thấy một số học bổng phù hợp với bạn. Nhấn vào từng thẻ để xem tóm tắt."


def _build_described_profile_reply_hint(profile: dict[str, Any], has_items: bool) -> str:
    if not has_items:
        return "Tôi chưa tìm thấy học bổng phù hợp với hồ sơ được mô tả."

    details: list[str] = []
    major = _format_profile_field(profile.get("major"))
    faculty = _format_profile_field(profile.get("faculty"))
    university = _format_profile_field(profile.get("university") or profile.get("school"))
    gpa = _format_profile_field(profile.get("gpa"))

    if major:
        details.append(f"ngành {major}")
    if faculty:
        details.append(f"khoa {faculty}")
    if university:
        details.append(f"trường {university}")
    if gpa:
        details.append(f"GPA {gpa}")

    if details:
        return (
            f"Dựa trên hồ sơ bạn mô tả ({', '.join(details)}), "
            "tôi đề xuất các học bổng phù hợp dưới đây. Nhấn vào từng thẻ để xem tóm tắt."
        )

    return "Dựa trên thông tin bạn mô tả, tôi đề xuất các học bổng phù hợp dưới đây. Nhấn vào từng thẻ để xem tóm tắt."


def _build_latest_reply_hint(has_items: bool) -> str:
    if not has_items:
        return "Tôi chưa tìm thấy học bổng mới nhất từ dữ liệu hiện tại."
    return "Tôi đã tìm thấy các học bổng mới cập nhật gần đây. Nhấn vào từng thẻ để xem tóm tắt."


def _extract_scholarship_search_criteria(user_query: str) -> dict[str, Any]:
    text = user_query or ""
    normalized = _normalize_text_for_count(text)
    profile_bits = _extract_query_profile(text)
    criteria: dict[str, Any] = {
        "major": profile_bits.get("major"),
        "university": profile_bits.get("university") or profile_bits.get("school"),
        "faculty": profile_bits.get("faculty"),
        "gpa": profile_bits.get("gpa"),
        "sort": "relevance",
        "requirement_complexity": None,
        "gpa_preference": None,
        "keywords": text,
    }

    if any(term in normalized for term in ["moi nhat", "gan day", "cap nhat", "latest", "recent"]):
        criteria["sort"] = "latest"
    if any(term in normalized for term in ["sap het han", "gan het han", "deadline gan", "deadline som"]):
        criteria["sort"] = "deadline"
    if any(term in normalized for term in ["yeu cau don gian", "de nop", "it yeu cau", "don gian"]):
        criteria["requirement_complexity"] = "simple"
    if any(term in normalized for term in ["yeu cau phuc tap", "nhieu yeu cau", "kho nop", "phuc tap"]):
        criteria["requirement_complexity"] = "complex"
    if any(term in normalized for term in ["gpa thap", "diem thap", "gpa khong cao"]):
        criteria["gpa_preference"] = "low"
    if any(term in normalized for term in ["gpa cao", "diem cao"]):
        criteria["gpa_preference"] = "high"

    subject_aliases = [
        ("IT", [" it ", "cong nghe thong tin", "information technology"]),
        ("Computer Science", ["computer science", "khoa hoc may tinh"]),
        ("Marketing", ["marketing"]),
        ("Business", ["business", "kinh doanh"]),
        ("AI", [" ai ", "artificial intelligence", "tri tue nhan tao"]),
    ]
    padded = f" {normalized} "
    if not criteria.get("major"):
        for label, aliases in subject_aliases:
            if any(alias in padded for alias in aliases):
                criteria["major"] = label
                break

    university_match = re.search(r"\b([A-Z][A-Z0-9]{2,10})\b", text)
    if university_match and not criteria.get("university"):
        criteria["university"] = university_match.group(1)

    return {key: value for key, value in criteria.items() if value not in (None, "", [])}


def _criteria_label(criteria: dict[str, Any]) -> str:
    labels: list[str] = []
    if criteria.get("sort") == "latest":
        labels.append("mới cập nhật gần đây")
    elif criteria.get("sort") == "deadline":
        labels.append("gần hạn nộp")
    if criteria.get("major"):
        labels.append(f"ngành {criteria['major']}")
    if criteria.get("university"):
        labels.append(f"trường {criteria['university']}")
    if criteria.get("gpa"):
        labels.append(f"GPA {criteria['gpa']}")
    if criteria.get("gpa_preference") == "low":
        labels.append("yêu cầu GPA thấp")
    if criteria.get("gpa_preference") == "high":
        labels.append("yêu cầu GPA cao")
    if criteria.get("requirement_complexity") == "simple":
        labels.append("yêu cầu đơn giản")
    if criteria.get("requirement_complexity") == "complex":
        labels.append("yêu cầu phức tạp")
    return ", ".join(labels)


def _build_criteria_reply_hint(criteria: dict[str, Any], has_items: bool) -> str:
    if not has_items:
        return "Tôi chưa tìm thấy học bổng phù hợp với tiêu chí bạn đưa ra."
    label = _criteria_label(criteria)
    if label:
        return f"Tôi đã tìm thấy các học bổng theo tiêu chí {label}. Nhấn vào từng thẻ để xem tóm tắt."
    return "Tôi đã tìm thấy một số học bổng theo tiêu chí bạn yêu cầu. Nhấn vào từng thẻ để xem tóm tắt."


def _match_level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _coverage_text(row: dict[str, Any]) -> str | None:
    amount = row.get("amount")
    currency = row.get("currency")
    if amount is not None and currency:
        try:
            amount_text = f"{float(amount):,.0f}".replace(",", ".")
        except (TypeError, ValueError):
            amount_text = str(amount)
        return f"{amount_text} {currency}"
    benefits = _shorten(row.get("benefits"), 80)
    if benefits:
        return benefits
    return _shorten(row.get("category_name"), 80)


def _requirement_summary(
    row: dict[str, Any],
    requirement_items: list[dict[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    requirements: dict[str, Any] = {"gpa": None, "language": None, "year_level": None, "other": []}
    minimum_gpa = row.get("minimum_gpa")
    if minimum_gpa is not None:
        scale = row.get("minimum_gpa_scale") or 4
        requirements["gpa"] = f"GPA >= {minimum_gpa}/{scale}"

    for item in requirement_items:
        title = str(item.get("title") or "")
        description = str(item.get("description") or "")
        text = " ".join(part for part in [title, description] if part).strip()
        text_lower = text.lower()
        if not text:
            continue
        if requirements["language"] is None and any(k in text_lower for k in ["ielts", "toeic", "toefl", "language"]):
            requirements["language"] = _shorten(text, 80)
        elif requirements["year_level"] is None and any(k in text_lower for k in ["year", "nam", "năm", "semester"]):
            requirements["year_level"] = _shorten(text, 80)
        elif len(requirements["other"]) < 3:
            requirements["other"].append(_shorten(text, 80))

    important = requirements["gpa"] or requirements["language"] or requirements["year_level"]
    if not important and requirements["other"]:
        important = requirements["other"][0]
    return requirements, important


def _benefit_list(row: dict[str, Any]) -> list[str]:
    values = _as_list(row.get("benefits"))
    if values:
        return [_shorten(value, 80) for value in values[:4] if _shorten(value, 80)]
    coverage = _coverage_text(row)
    return [coverage] if coverage else []


def _target_audience(row: dict[str, Any]) -> list[str]:
    audience: list[str] = []
    level = _first_text(row.get("level"))
    if level:
        audience.append(level)
    universities = _as_list(row.get("target_universities"))
    audience.extend(universities[:2])
    return audience[:4]


def _recommendation_reason(
    row: dict[str, Any],
    profile: dict[str, Any],
    matched_terms: list[str],
) -> str:
    major = _first_text(profile.get("major"))
    provider = _first_text(row.get("provider"), row.get("category_name"))
    if matched_terms:
        return f"Phù hợp với các thông tin trong hồ sơ của bạn: {', '.join(matched_terms[:3])}."
    if major:
        return f"Phù hợp với nền tảng/ngành học {major} của bạn."
    if provider:
        return f"Là học bổng từ {provider} có liên quan đến hồ sơ của bạn."
    return "Đây là học bổng gần phù hợp nhất trong dữ liệu hiện có."


def _build_recommendation_item(
    row: dict[str, Any],
    profile: dict[str, Any],
    requirement_items: list[dict[str, Any]],
    score: float,
    matched_terms: list[str],
) -> dict[str, Any]:
    requirements, important_requirement = _requirement_summary(row, requirement_items)
    target_universities = _as_list(row.get("target_universities"))
    return {
        "id": str(row.get("id")),
        "title": _first_text(row.get("name")) or "Học bổng",
        "country": None,
        "university": target_universities[0] if target_universities else None,
        "provider": _first_text(row.get("provider")),
        "category": _first_text(row.get("category_name")),
        "majors": _as_list(row.get("target_majors")),
        "coverage": _coverage_text(row),
        "important_requirement": important_requirement,
        "requirements": requirements,
        "benefits": _benefit_list(row),
        "deadline": _serialize(row.get("application_deadline")),
        "target_audience": _target_audience(row),
        "match_reason": _recommendation_reason(row, profile, matched_terms),
        "match_level": _match_level(score),
        "match_score": round(score, 3),
    }


async def _fetch_recommendation_sources(
    active_only: bool,
    open_only: bool,
    now: datetime,
) -> tuple[list[Any], dict[str, list[dict[str, Any]]]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        scholarship_rows = await conn.fetch(
            """
            SELECT s.id,
                   s.name,
                   s.description,
                   s.eligibility_criteria,
                   s.benefits,
                   s.provider,
                   s.target_majors,
                   s.target_universities,
                   s.minimum_gpa,
                   s.minimum_gpa_scale,
                   s.amount,
                   s.currency,
                   s.level,
                   s.is_active,
                   s.application_deadline,
                   s.result_announcement_date,
                   s.updated_at,
                   sc.name AS category_name
            FROM scholarships s
            LEFT JOIN scholarship_categories sc ON sc.id = s.category_id
            WHERE ($1::boolean = false OR s.is_active = true)
              AND ($2::boolean = false OR (s.is_active = true AND (s.application_deadline IS NULL OR s.application_deadline >= $3)))
            ORDER BY s.updated_at DESC NULLS LAST
            LIMIT 300
            """,
            active_only,
            open_only,
            now,
        )

        scholarship_ids = [row["id"] for row in scholarship_rows if row.get("id")]
        requirement_map: dict[str, list[dict[str, Any]]] = {}
        if scholarship_ids:
            requirement_rows = await conn.fetch(
                """
                SELECT scholarship_id,
                       title,
                       description,
                       is_required,
                       sort_order
                FROM scholarship_requirements
                WHERE scholarship_id = ANY($1::uuid[])
                ORDER BY is_required DESC, sort_order ASC
                """,
                scholarship_ids,
            )
            for item in requirement_rows:
                item_dict = dict(item)
                requirement_map.setdefault(str(item_dict.get("scholarship_id")), []).append(item_dict)

    return list(scholarship_rows), requirement_map


def _rank_recommendation_items(
    scholarship_rows: list[Any],
    requirement_map: dict[str, list[dict[str, Any]]],
    profile: dict[str, Any],
    safe_limit: int,
    now: datetime,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for row in scholarship_rows:
        row_dict = dict(row)
        score, matched_terms = _score_profile_match(profile, row_dict)

        profile_major_tokens = set(_tokenize(str(profile.get("major") or "")))
        target_major_tokens = set(_tokenize(" ".join(_as_list(row_dict.get("target_majors")))))
        if profile_major_tokens and target_major_tokens and profile_major_tokens & target_major_tokens:
            score = min(1.0, score + 0.25)

        profile_gpa = profile.get("gpa")
        minimum_gpa = row_dict.get("minimum_gpa")
        try:
            if profile_gpa is not None and minimum_gpa is not None:
                if float(profile_gpa) >= float(minimum_gpa):
                    score = min(1.0, score + 0.15)
                else:
                    score = max(0.0, score - 0.15)
        except (TypeError, ValueError):
            pass

        deadline = row_dict.get("application_deadline")
        is_open = bool(row_dict.get("is_active") and (deadline is None or deadline >= now))
        if is_open:
            score = min(1.0, score + 0.05)

        sid = str(row_dict.get("id"))
        ranked.append(
            {
                "score": round(score, 6),
                "is_open": is_open,
                "item": _build_recommendation_item(
                    row_dict,
                    profile,
                    requirement_map.get(sid, []),
                    score,
                    matched_terms,
                ),
            }
        )

    ranked.sort(key=lambda value: (value["score"], value["is_open"]), reverse=True)
    return [entry["item"] for entry in ranked[:safe_limit]]


def _build_latest_items(
    scholarship_rows: list[Any],
    requirement_map: dict[str, list[dict[str, Any]]],
    safe_limit: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in scholarship_rows[:safe_limit]:
        row_dict = dict(row)
        sid = str(row_dict.get("id"))
        item = _build_recommendation_item(row_dict, {}, requirement_map.get(sid, []), 0.45, [])
        item["match_reason"] = "Học bổng được cập nhật gần đây."
        item["match_level"] = "medium"
        item["match_score"] = None
        items.append(item)
    return items


def _criteria_score(
    row: dict[str, Any],
    requirement_items: list[dict[str, Any]],
    criteria: dict[str, Any],
    now: datetime,
) -> tuple[float, list[str]]:
    score = 0.0
    matched: list[str] = []
    haystack = " ".join(
        str(part or "")
        for part in [
            row.get("name"),
            row.get("description"),
            row.get("eligibility_criteria"),
            row.get("benefits"),
            row.get("provider"),
            row.get("category_name"),
            " ".join(_as_list(row.get("target_majors"))),
            " ".join(_as_list(row.get("target_universities"))),
        ]
    )
    haystack_tokens = set(_tokenize(haystack))

    major = criteria.get("major")
    if major:
        major_tokens = set(_tokenize(str(major)))
        if major_tokens and major_tokens & haystack_tokens:
            score += 0.35
            matched.append(f"ngành {major}")

    university = criteria.get("university")
    if university:
        university_tokens = set(_tokenize(str(university)))
        if university_tokens and university_tokens & haystack_tokens:
            score += 0.25
            matched.append(f"trường {university}")

    gpa = criteria.get("gpa")
    minimum_gpa = row.get("minimum_gpa")
    try:
        if gpa is not None and minimum_gpa is not None:
            if float(gpa) >= float(minimum_gpa):
                score += 0.2
                matched.append(f"GPA đáp ứng yêu cầu {minimum_gpa}")
            else:
                score -= 0.2
    except (TypeError, ValueError):
        pass

    gpa_preference = criteria.get("gpa_preference")
    try:
        min_gpa_value = float(minimum_gpa) if minimum_gpa is not None else None
        if gpa_preference == "low" and (min_gpa_value is None or min_gpa_value <= 3.0):
            score += 0.2
            matched.append("yêu cầu GPA thấp")
        if gpa_preference == "high" and min_gpa_value is not None and min_gpa_value >= 3.4:
            score += 0.2
            matched.append("yêu cầu GPA cao")
    except (TypeError, ValueError):
        pass

    required_count = sum(1 for item in requirement_items if item.get("is_required"))
    total_requirement_count = len(requirement_items)
    complexity = criteria.get("requirement_complexity")
    if complexity == "simple" and total_requirement_count <= 3:
        score += 0.2
        matched.append("yêu cầu đơn giản")
    if complexity == "complex" and (required_count >= 3 or total_requirement_count >= 5):
        score += 0.2
        matched.append("yêu cầu phức tạp")

    deadline = row.get("application_deadline")
    is_open = bool(row.get("is_active") and (deadline is None or deadline >= now))
    if is_open:
        score += 0.05

    return round(max(0.0, min(score, 1.0)), 6), matched


def _criteria_reason(criteria: dict[str, Any], matched_terms: list[str]) -> str:
    if matched_terms:
        return f"Phù hợp với tiêu chí: {', '.join(matched_terms[:4])}."
    if criteria.get("sort") == "latest":
        return "Học bổng được cập nhật gần đây."
    if criteria.get("sort") == "deadline":
        return "Học bổng có hạn nộp gần."
    return "Phù hợp gần nhất với tiêu chí tìm kiếm."


def _rank_criteria_items(
    scholarship_rows: list[Any],
    requirement_map: dict[str, list[dict[str, Any]]],
    criteria: dict[str, Any],
    safe_limit: int,
    now: datetime,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for row in scholarship_rows:
        row_dict = dict(row)
        sid = str(row_dict.get("id"))
        requirements = requirement_map.get(sid, [])
        score, matched_terms = _criteria_score(row_dict, requirements, criteria, now)
        item = _build_recommendation_item(row_dict, {}, requirements, score, [])
        item["match_reason"] = _criteria_reason(criteria, matched_terms)
        item["match_score"] = round(score, 3)
        ranked.append(
            {
                "score": score,
                "updated_at": row_dict.get("updated_at") or datetime.min,
                "deadline": row_dict.get("application_deadline") or datetime.max,
                "item": item,
            }
        )

    if criteria.get("sort") == "latest":
        ranked.sort(key=lambda value: value["updated_at"], reverse=True)
    elif criteria.get("sort") == "deadline":
        ranked.sort(key=lambda value: value["deadline"])
    else:
        ranked.sort(key=lambda value: (value["score"], value["updated_at"]), reverse=True)

    return [entry["item"] for entry in ranked[:safe_limit]]


@tool
async def get_my_full_profile(config: RunnableConfig) -> str:
	"""
	Lấy toàn bộ thông tin hồ sơ của sinh viên hiện tại (cá nhân + học vấn + kỹ năng + sở thích
	+ học bổng đã đăng ký + việc làm đã lưu + CLB tham gia + chứng chỉ).

	Trả về:
		JSON string với các nhóm dữ liệu chính để dùng cho matching học bổng.
	"""
	user_id = _uid(config)

	try:
		pool = await get_pool()
		async with pool.acquire() as conn:
			user_row = await conn.fetchrow(
				"""
				SELECT u.id AS user_id,
					   u.account_id,
					   a.email AS account_email,
					   up.full_name,
					   up.gender,
					   up.date_of_birth,
					   up.phone_number,
					   up.email AS profile_email,
					   up.address,
					   up.city,
					   up.country,
					   up.province_id,
					   up.avatar_url,
					   up.cover_photo_url,
					   up.headline,
					   up.summary,
					   up.career_goal,
					   up.interests AS interest_ids,
					   up.skill AS skill_ids,
					   up.linkedin_url,
					   up.portfolio_url,
					   up.resume_url,
					   up.personal_website,
					   up.visibility,
					   up.created_at AS profile_created_at,
					   up.updated_at AS profile_updated_at
				FROM users u
				LEFT JOIN accounts a ON a.account_id = u.account_id
				LEFT JOIN users_profiles up ON up.user_id = u.id
				WHERE u.id = $1
				LIMIT 1
				""",
				user_id,
			)

			if not user_row:
				return json.dumps(
					{"error": "Không tìm thấy sinh viên.", "user_id": user_id},
					ensure_ascii=False,
				)

			account_id = user_row.get("account_id")
			skill_ids = _ensure_uuid_list(user_row.get("skill_ids"))
			interest_ids = _ensure_uuid_list(user_row.get("interest_ids"))

			academic_rows = await conn.fetch(
				"""
				SELECT id,
					   university,
					   student_code,
					   education_program,
					   degree_level,
					   faculty,
					   major,
					   minor,
					   program_type,
					   gpa,
					   enrollment_year,
					   expected_graduation_year,
					   current_status,
					   current_year,
					   current_semester,
					   created_at,
					   updated_at
				FROM student_academic_profiles
				WHERE user_id = $1
				ORDER BY updated_at DESC NULLS LAST
				""",
				user_id,
			)
			skills = []
			if skill_ids:
				skills = await conn.fetch(
					"""
					SELECT id, name, description, created_at, updated_at
					FROM skills
					WHERE id = ANY($1::uuid[])
					""",
					skill_ids,
				)

			interests = []
			if interest_ids:
				interests = await conn.fetch(
					"""
					SELECT *
					FROM profile_interests
					WHERE id = ANY($1::uuid[])
					""",
					interest_ids,
				)

			scholarship_rows = await conn.fetch(
				"""
				SELECT ss.id,
					   ss.scholarship_id,
					   ss.status,
					   ss.application_date,
					   ss.decision_date,
					   ss.awarded_amount,
					   ss.currency,
					   ss.submitted_form_url,
					   ss.note,
					   ss.feedback,
					   ss.created_at,
					   ss.updated_at,
					   s.name AS scholarship_name,
					   s.provider,
					   s.amount AS scholarship_amount,
					   s.currency AS scholarship_currency,
					   s.application_deadline,
					   s.result_announcement_date
				FROM student_scholarships ss
				JOIN scholarships s ON s.id = ss.scholarship_id
				WHERE ss.user_id = $1
				ORDER BY ss.created_at DESC
				""",
				user_id,
			)

			saved_job_rows = await conn.fetch(
				"""
				SELECT usj.id,
					   usj.job_id,
					   usj.note,
					   usj.saved_at,
					   j.title,
					   j.company_id,
					   j.job_type,
					   j.salary_min,
					   j.salary_max,
					   j.currency_id,
					   j.application_method,
					   j.deadline,
					   j.is_active
				FROM user_saved_jobs usj
				JOIN jobs j ON j.id = usj.job_id
				WHERE usj.user_id = $1
				ORDER BY usj.saved_at DESC
				""",
				user_id,
			)

			club_rows = []
			if account_id:
				club_rows = await conn.fetch(
					"""
					SELECT m.id AS membership_id,
						   m.role,
						   m.status,
						   m.joined_at,
						   m.left_at,
						   c.id AS club_id,
						   c.name,
						   c.description,
						   c.tags,
						   c.members_count,
						   c.events_count,
						   c.posts_count,
						   c.banner_url,
						   c.logo_url,
						   c.contact_email,
						   c.website_url,
						   c.meeting_schedule,
						   c.meeting_location,
						   c.status AS club_status
					FROM members m
					JOIN clubs c ON c.id = m.entity_id
					WHERE m.account_id = $1
					  AND m.entity_type = 'club'
					ORDER BY m.joined_at DESC NULLS LAST
					""",
					account_id,
				)

			certificate_rows = await conn.fetch(
				"""
				SELECT sc.id,
					   sc.certificate_id,
					   sc.certificate_number,
					   sc.issued_date,
					   sc.expiry_date,
					   sc.certificate_file_url,
					   sc.verification_code,
					   sc.verification_url,
					   sc.final_score,
					   sc.completion_date,
					   sc.status,
					   sc.revocation_reason,
					   sc.revoked_at,
					   sc.created_at,
					   sc.updated_at,
					   c.name AS certificate_name,
					   c.description AS certificate_description,
					   c.issuing_organization,
					   c.certificate_type
				FROM student_certificates sc
				JOIN certificates c ON c.id = sc.certificate_id
				WHERE sc.user_id = $1
				ORDER BY sc.created_at DESC
				""",
				user_id,
			)

		payload = {
			"user": _serialize(dict(user_row)),
			"academics": _serialize([dict(r) for r in academic_rows]),
			"skills": _serialize([dict(r) for r in skills]),
			"interests": _serialize([dict(r) for r in interests]),
			"scholarships": _serialize([dict(r) for r in scholarship_rows]),
			"saved_jobs": _serialize([dict(r) for r in saved_job_rows]),
			"clubs": _serialize([dict(r) for r in club_rows]),
			"certificates": _serialize([dict(r) for r in certificate_rows]),
			"counts": {
				"academics": len(academic_rows),
				"skills": len(skills),
				"interests": len(interests),
				"scholarships": len(scholarship_rows),
				"saved_jobs": len(saved_job_rows),
				"clubs": len(club_rows),
				"certificates": len(certificate_rows),
			},
		}

		return json.dumps(payload, ensure_ascii=False)
	except Exception as exc:  # pragma: no cover - defensive fallback for tool runtime
		logger.exception("get_my_full_profile_failed", error=str(exc), user_id=user_id)
		return json.dumps(
			{"error": f"Lỗi lấy hồ sơ sinh viên: {str(exc)}"},
			ensure_ascii=False,
		)

@tool
async def get_scholarship_recommendations_for_chat(
    config: RunnableConfig,
    user_query: str = "",
    max_results: int = 6,
    active_only: bool = True,
    open_only: bool = False,
) -> str:
    """
    Build compact structured scholarship recommendations for chat cards.

    Returns JSON with a short reply_hint and scholarship_recommendations metadata.
    """
    user_id = _uid(config)
    requested_count = _extract_requested_recommendation_count(user_query)
    desired_count = requested_count if requested_count is not None else max_results
    safe_limit = max(1, min(int(desired_count), 8))
    now = datetime.utcnow()

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            user_row = await conn.fetchrow(
                """
                SELECT up.country,
                       up.career_goal,
                       up.summary,
                       up.interests AS interest_ids,
                       up.skill AS skill_ids
                FROM users u
                LEFT JOIN users_profiles up ON up.user_id = u.id
                WHERE u.id = $1
                LIMIT 1
                """,
                user_id,
            )

            academic_rows = await conn.fetch(
                """
                SELECT university,
                       education_program,
                       degree_level,
                       faculty,
                       major,
                       minor,
                       program_type,
                       gpa,
                       current_year,
                       current_semester
                FROM student_academic_profiles
                WHERE user_id = $1
                ORDER BY updated_at DESC NULLS LAST
                """,
                user_id,
            )

            skill_ids = _ensure_uuid_list(user_row.get("skill_ids") if user_row else None)
            interest_ids = _ensure_uuid_list(user_row.get("interest_ids") if user_row else None)
            skill_rows = []
            interest_rows = []
            if skill_ids:
                skill_rows = await conn.fetch("SELECT name FROM skills WHERE id = ANY($1::uuid[])", skill_ids)
            if interest_ids:
                interest_rows = await conn.fetch("SELECT name FROM profile_interests WHERE id = ANY($1::uuid[])", interest_ids)

            scholarship_rows = await conn.fetch(
                """
                SELECT s.id,
                       s.name,
                       s.description,
                       s.eligibility_criteria,
                       s.benefits,
                       s.provider,
                       s.target_majors,
                       s.target_universities,
                       s.minimum_gpa,
                       s.minimum_gpa_scale,
                       s.amount,
                       s.currency,
                       s.level,
                       s.is_active,
                       s.application_deadline,
                       s.result_announcement_date,
                       s.updated_at,
                       sc.name AS category_name
                FROM scholarships s
                LEFT JOIN scholarship_categories sc ON sc.id = s.category_id
                WHERE ($1::boolean = false OR s.is_active = true)
                  AND ($2::boolean = false OR (s.is_active = true AND (s.application_deadline IS NULL OR s.application_deadline >= $3)))
                ORDER BY s.updated_at DESC NULLS LAST
                LIMIT 300
                """,
                active_only,
                open_only,
                now,
            )

            scholarship_ids = [row["id"] for row in scholarship_rows if row.get("id")]
            requirement_map: dict[str, list[dict[str, Any]]] = {}
            if scholarship_ids:
                requirement_rows = await conn.fetch(
                    """
                    SELECT scholarship_id,
                           title,
                           description,
                           is_required,
                           sort_order
                    FROM scholarship_requirements
                    WHERE scholarship_id = ANY($1::uuid[])
                    ORDER BY is_required DESC, sort_order ASC
                    """,
                    scholarship_ids,
                )
                for item in requirement_rows:
                    item_dict = dict(item)
                    requirement_map.setdefault(str(item_dict.get("scholarship_id")), []).append(item_dict)

        profile_payload = {
            "user": _serialize(dict(user_row)) if user_row else {},
            "academics": _serialize([dict(row) for row in academic_rows]),
            "skills": _serialize([dict(row) for row in skill_rows]),
            "interests": _serialize([dict(row) for row in interest_rows]),
        }
        profile = _build_profile_summary(profile_payload, user_query)

        ranked: list[dict[str, Any]] = []
        for row in scholarship_rows:
            row_dict = dict(row)
            score, matched_terms = _score_profile_match(profile, row_dict)

            profile_major_tokens = set(_tokenize(str(profile.get("major") or "")))
            target_major_tokens = set(_tokenize(" ".join(_as_list(row_dict.get("target_majors")))))
            if profile_major_tokens and target_major_tokens and profile_major_tokens & target_major_tokens:
                score = min(1.0, score + 0.25)

            profile_gpa = profile.get("gpa")
            minimum_gpa = row_dict.get("minimum_gpa")
            try:
                if profile_gpa is not None and minimum_gpa is not None:
                    if float(profile_gpa) >= float(minimum_gpa):
                        score = min(1.0, score + 0.15)
                    else:
                        score = max(0.0, score - 0.15)
            except (TypeError, ValueError):
                pass

            deadline = row_dict.get("application_deadline")
            is_open = bool(row_dict.get("is_active") and (deadline is None or deadline >= now))
            if is_open:
                score = min(1.0, score + 0.05)

            sid = str(row_dict.get("id"))
            ranked.append(
                {
                    "score": round(score, 6),
                    "is_open": is_open,
                    "item": _build_recommendation_item(
                        row_dict,
                        profile,
                        requirement_map.get(sid, []),
                        score,
                        matched_terms,
                    ),
                }
            )

        ranked.sort(key=lambda value: (value["score"], value["is_open"]), reverse=True)
        items = [entry["item"] for entry in ranked[:safe_limit]]
        reply_hint = _build_recommendation_reply_hint(profile, bool(items))

        return json.dumps(
            {
                "reply_hint": reply_hint,
                "scholarship_recommendations": {
                    "kind": "scholarship_recommendations",
                    "basis": "profile_match",
                    "items": _serialize(items),
                },
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback for tool runtime
        logger.exception("get_scholarship_recommendations_for_chat_failed", error=str(exc), user_id=user_id)
        return json.dumps(
            {
                "error": f"Không thể tạo gợi ý học bổng: {str(exc)}",
                "reply_hint": "Tôi chưa thể tải gợi ý học bổng lúc này.",
            },
            ensure_ascii=False,
        )


@tool
async def search_scholarship_recommendations_by_criteria(
    user_query: str = "",
    max_results: int = 6,
    active_only: bool = True,
    open_only: bool = False,
) -> str:
    """
    Build compact scholarship cards from arbitrary search criteria.

    Use this for broad scholarship search that is not about the current user's
    profile: latest/recent, deadline, simple/complex requirements, GPA level,
    major, school/university, provider/category, or mixed criteria.
    """
    requested_count = _extract_requested_recommendation_count(user_query)
    desired_count = requested_count if requested_count is not None else max_results
    safe_limit = max(1, min(int(desired_count), 8))
    now = datetime.utcnow()

    try:
        criteria = _extract_scholarship_search_criteria(user_query)
        scholarship_rows, requirement_map = await _fetch_recommendation_sources(active_only, open_only, now)
        items = _rank_criteria_items(scholarship_rows, requirement_map, criteria, safe_limit, now)
        reply_hint = _build_criteria_reply_hint(criteria, bool(items))
        return json.dumps(
            {
                "reply_hint": reply_hint,
                "scholarship_recommendations": {
                    "kind": "scholarship_recommendations",
                    "basis": "criteria",
                    "items": _serialize(items),
                },
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback for tool runtime
        logger.exception("search_scholarship_recommendations_by_criteria_failed", error=str(exc))
        return json.dumps(
            {
                "error": f"Không thể tìm học bổng theo tiêu chí: {str(exc)}",
                "reply_hint": "Tôi chưa thể tải học bổng theo tiêu chí lúc này.",
            },
            ensure_ascii=False,
        )


@tool
async def get_scholarship_recommendations_for_described_profile(
    user_query: str = "",
    profile_json: str = "",
    max_results: int = 6,
    active_only: bool = True,
    open_only: bool = False,
) -> str:
    """
    Build compact scholarship cards for a profile described by the user.

    Use this when the user asks for another person, a hypothetical student, or
    gives GPA/school/major directly in the message. This tool does not read the
    current user's profile.
    """
    requested_count = _extract_requested_recommendation_count(user_query)
    desired_count = requested_count if requested_count is not None else max_results
    safe_limit = max(1, min(int(desired_count), 8))
    now = datetime.utcnow()

    try:
        parsed_profile: dict[str, Any] = {}
        if profile_json.strip():
            parsed = json.loads(profile_json)
            if isinstance(parsed, dict):
                parsed_profile = parsed
        query_profile = _extract_query_profile(user_query)
        profile = {**query_profile, **{k: v for k, v in parsed_profile.items() if v not in (None, "", [])}}
        if user_query:
            profile["keywords"] = user_query

        scholarship_rows, requirement_map = await _fetch_recommendation_sources(active_only, open_only, now)
        items = _rank_recommendation_items(scholarship_rows, requirement_map, profile, safe_limit, now)
        reply_hint = _build_described_profile_reply_hint(profile, bool(items))
        return json.dumps(
            {
                "reply_hint": reply_hint,
                "scholarship_recommendations": {
                    "kind": "scholarship_recommendations",
                    "basis": "described_profile_match",
                    "items": _serialize(items),
                },
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback for tool runtime
        logger.exception("get_scholarship_recommendations_for_described_profile_failed", error=str(exc))
        return json.dumps(
            {
                "error": f"Không thể tạo gợi ý học bổng theo hồ sơ được mô tả: {str(exc)}",
                "reply_hint": "Tôi chưa thể tải gợi ý học bổng cho hồ sơ được mô tả lúc này.",
            },
            ensure_ascii=False,
        )


@tool
async def get_latest_scholarship_recommendations_for_chat(
    user_query: str = "",
    max_results: int = 6,
    active_only: bool = True,
    open_only: bool = False,
) -> str:
    """
    Build compact scholarship cards sorted by latest update.

    Use this for "học bổng mới nhất", "gần đây", "latest", or broad discovery
    requests that do not ask for compatibility with a user/profile.
    """
    requested_count = _extract_requested_recommendation_count(user_query)
    desired_count = requested_count if requested_count is not None else max_results
    safe_limit = max(1, min(int(desired_count), 8))
    now = datetime.utcnow()

    try:
        criteria = _extract_scholarship_search_criteria(user_query or "học bổng mới nhất gần đây")
        criteria["sort"] = "latest"
        scholarship_rows, requirement_map = await _fetch_recommendation_sources(active_only, open_only, now)
        items = _rank_criteria_items(scholarship_rows, requirement_map, criteria, safe_limit, now)
        reply_hint = _build_criteria_reply_hint(criteria, bool(items))
        return json.dumps(
            {
                "reply_hint": reply_hint,
                "scholarship_recommendations": {
                    "kind": "scholarship_recommendations",
                    "basis": "criteria",
                    "items": _serialize(items),
                },
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback for tool runtime
        logger.exception("get_latest_scholarship_recommendations_for_chat_failed", error=str(exc))
        return json.dumps(
            {
                "error": f"Không thể tải học bổng mới nhất: {str(exc)}",
                "reply_hint": "Tôi chưa thể tải danh sách học bổng mới nhất lúc này.",
            },
            ensure_ascii=False,
        )


@tool
async def match_scholarships_for_profile(
    profile_json: str,
    max_results: int = 10,
    active_only: bool = True,
    open_only: bool = False,
) -> str:
    """
    Rank scholarships by compatibility with a student profile.

    Args:
        profile_json: JSON string with fields like major, university, skills, interests.
        max_results: Number of candidates to return (1-20).
        active_only: If true, only search scholarships with is_active = true.
        open_only: If true, only include scholarships still open for application.

    Returns:
        JSON string with best_match and ranked candidates.
    """
    if not (profile_json or "").strip():
        return json.dumps(
            {
                "error": "profile_json is required.",
                "hint": "Ví dụ: {'major':'IT','university':'FPT','skills':['python','ai']}"
            },
            ensure_ascii=False,
        )

    try:
        profile = json.loads(profile_json)
    except json.JSONDecodeError:
        return json.dumps(
            {
                "error": "profile_json must be valid JSON.",
            },
            ensure_ascii=False,
        )

    if not isinstance(profile, dict):
        return json.dumps(
            {
                "error": "profile_json must be a JSON object.",
            },
            ensure_ascii=False,
        )

    safe_limit = max(1, min(int(max_results), 20))
    profile_text = _build_profile_text(profile)
    if not profile_text:
        return json.dumps(
            {
                "error": "Profile is missing searchable fields.",
                "required_fields": ["major", "university", "skills", "interests", "keywords"],
            },
            ensure_ascii=False,
        )

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.id,
                       s.name,
                       s.description,
                       s.eligibility_criteria,
                       s.benefits,
                       s.provider,
                       s.is_active,
                       s.application_deadline,
                       s.result_announcement_date,
                       s.updated_at,
                       sc.name AS category_name
                FROM scholarships s
                LEFT JOIN scholarship_categories sc ON sc.id = s.category_id
                WHERE ($1::boolean = false OR s.is_active = true)
                ORDER BY s.updated_at DESC NULLS LAST
                LIMIT 300
                """,
                active_only,
            )

        ranked: list[dict[str, Any]] = []
        now = datetime.utcnow()
        for row in rows:
            row_dict = dict(row)
            deadline = row_dict.get("application_deadline")
            is_open = bool(row_dict.get("is_active") and (deadline is None or deadline >= now))
            if open_only and not is_open:
                continue

            score, matched_terms = _score_profile_match(profile, row_dict)
            ranked.append(
                {
                    "id": row_dict.get("id"),
                    "name": row_dict.get("name"),
                    "provider": row_dict.get("provider"),
                    "category": row_dict.get("category_name"),
                    "is_active": row_dict.get("is_active"),
                    "application_deadline": row_dict.get("application_deadline"),
                    "result_announcement_date": row_dict.get("result_announcement_date"),
                    "is_open_for_application": is_open,
                    "score": score,
                    "matched_terms": matched_terms,
                }
            )

        ranked.sort(key=lambda item: (item["score"], bool(item.get("is_open_for_application"))), reverse=True)
        top = ranked[:safe_limit]
        best = top[0] if top else None
        confidence = "high" if best and best["score"] >= 0.7 else "medium" if best and best["score"] >= 0.5 else "low"

        payload = {
            "profile_summary": profile,
            "search_mode": {
                "accent_insensitive": True,
                "active_only": active_only,
                "open_only": open_only,
            },
            "best_match": _serialize(best) if best else None,
            "best_match_id": _serialize(best.get("id")) if best else None,
            "confidence": confidence,
            "candidates": _serialize(top),
        }

        if best and best["score"] < 0.5:
            payload["warning"] = (
                "Kết quả khớp thấp. Nên kiểm tra lại profile hoặc xem danh sách candidates."
            )

        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:  # pragma: no cover - defensive fallback for tool runtime
        logger.exception("match_scholarships_for_profile_failed", error=str(exc))
        return json.dumps(
            {
                "error": f"Lỗi tìm học bổng phù hợp: {str(exc)}",
            },
            ensure_ascii=False,
        )
