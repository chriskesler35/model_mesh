"""Stats endpoints."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.schemas import CostSummary, UsageSummary
from app.middleware.auth import verify_api_key

router = APIRouter(prefix="/v1/stats", tags=["stats"], dependencies=[Depends(verify_api_key)])


@router.get("/costs", response_model=CostSummary)
async def get_costs(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db)
):
    """Get cost summary for the last N days."""
    from app.models import RequestLog, Model
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get total cost
    total_result = await db.execute(
        select(func.sum(RequestLog.estimated_cost)).where(
            RequestLog.created_at >= start_date
        )
    )
    total_cost = float(total_result.scalar() or 0)
    
    # Get cost by model
    model_costs_result = await db.execute(
        select(Model.model_id, func.sum(RequestLog.estimated_cost))
        .join(Model, RequestLog.model_id == Model.id)
        .where(RequestLog.created_at >= start_date)
        .group_by(Model.model_id)
    )
    by_model = {row[0]: float(row[1]) for row in model_costs_result}
    
    # Get cost by provider
    provider_costs_result = await db.execute(
        select(Model.provider_id, func.sum(RequestLog.estimated_cost))
        .join(Model, RequestLog.model_id == Model.id)
        .where(RequestLog.created_at >= start_date)
        .group_by(Model.provider_id)
    )
    by_provider = {str(row[0]): float(row[1]) for row in provider_costs_result}
    
    return CostSummary(
        total_cost=total_cost,
        by_model=by_model,
        by_provider=by_provider,
        period_start=start_date,
        period_end=datetime.utcnow()
    )


@router.get("/usage", response_model=UsageSummary)
async def get_usage(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db)
):
    """Get usage summary for the last N days."""
    from app.models import RequestLog, Model
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get totals
    total_result = await db.execute(
        select(
            func.sum(RequestLog.input_tokens),
            func.sum(RequestLog.output_tokens),
            func.count(RequestLog.id)
        ).where(RequestLog.created_at >= start_date)
    )
    row = total_result.one()
    total_input = int(row[0] or 0)
    total_output = int(row[1] or 0)
    total_requests = int(row[2] or 0)
    
    # Get successful requests count separately
    success_result = await db.execute(
        select(func.count(RequestLog.id)).where(
            (RequestLog.created_at >= start_date) & 
            (RequestLog.success == True)
        )
    )
    successful_requests = int(success_result.scalar() or 0)
    
    success_rate = successful_requests / total_requests if total_requests > 0 else 1.0
    
    # Get usage by model
    model_usage_result = await db.execute(
        select(
            Model.model_id,
            func.sum(RequestLog.input_tokens),
            func.sum(RequestLog.output_tokens),
            func.count(RequestLog.id)
        )
        .join(Model, RequestLog.model_id == Model.id)
        .where(RequestLog.created_at >= start_date)
        .group_by(Model.model_id)
    )
    by_model = {}
    for row in model_usage_result:
        by_model[row[0]] = {
            "input_tokens": int(row[1] or 0),
            "output_tokens": int(row[2] or 0),
            "requests": int(row[3] or 0)
        }
    
    return UsageSummary(
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_requests=total_requests,
        success_rate=success_rate,
        by_model=by_model,
        by_provider={},
        period_start=start_date,
        period_end=datetime.utcnow()
    )