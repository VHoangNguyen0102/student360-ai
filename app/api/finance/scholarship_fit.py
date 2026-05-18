"""Scholarship fit analysis API."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.domains.finance.models.scholarship_fit import (
    ScholarshipFitAnalysis,
    ScholarshipFitAnalysisRequest,
)
from app.domains.finance.scholarships.fit_analysis import analyze_scholarship_fit
from app.utils.auth import verify_service_token

router = APIRouter()


@router.post("/scholarships/{scholarship_id}/fit-analysis", response_model=ScholarshipFitAnalysis)
async def scholarship_fit_analysis(
    scholarship_id: str,
    req: ScholarshipFitAnalysisRequest,
    _: str = Depends(verify_service_token),
) -> ScholarshipFitAnalysis:
    return await analyze_scholarship_fit(scholarship_id, req)
