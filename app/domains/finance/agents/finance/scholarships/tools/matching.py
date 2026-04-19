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
from langchain_core.tools import tool

from app.core.database import get_pool

logger = structlog.get_logger()


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

		required_requirement_count = sum(1 for item in requirement_items if item.get("is_required"))
		required_document_count = sum(1 for item in document_items if item.get("is_required"))

		deadline = scholarship_data.get("application_deadline")
		is_open_for_application = bool(
			scholarship_data.get("is_active")
			and (deadline is None or deadline >= datetime.utcnow())
		)

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

		if not requirement_items:
			response["warning_requirements"] = "Học bổng chưa có requirement checklist."
		if not document_items:
			response["warning_documents"] = "Học bổng chưa có document checklist."

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
