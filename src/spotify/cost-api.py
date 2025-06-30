"""
Cost tracking API endpoints
"""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.auth import get_current_user, User
from src.cost_tracker import get_cost_tracker
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/costs", tags=["costs"])


# Response Models
class CostSummary(BaseModel):
    """Cost summary response"""
    total_cost: float
    service_breakdown: dict
    period_days: int
    start_date: datetime
    end_date: datetime


class DailyCost(BaseModel):
    """Daily cost breakdown"""
    date: str
    total_cost: float
    service_costs: dict
    api_calls: int


class UserCost(BaseModel):
    """Per-user cost breakdown"""
    user_id: str
    email: Optional[str]
    total_cost: float
    service_breakdown: dict
    api_calls: int


class BudgetStatus(BaseModel):
    """Budget status response"""
    daily_spent: float
    daily_limit: float
    daily_remaining: float
    weekly_spent: float
    weekly_limit: float
    weekly_remaining: float
    monthly_spent: float
    monthly_limit: float
    monthly_remaining: float
    at_risk: bool


# API Endpoints
@router.get("/summary", response_model=CostSummary)
async def get_cost_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    current_user: User = Depends(get_current_user)
):
    """Get cost summary for the specified period"""
    tracker = get_cost_tracker()
    
    # Get cost data
    summary = await tracker.get_cost_summary(days=days)
    
    # Calculate service breakdown
    service_breakdown = {
        "aws_cost_explorer": float(summary.aws_costs),
        "spotify_api": float(summary.spotify_costs or 0),
        "transcription": float(summary.transcription_costs or 0),
        "llm_api": float(summary.llm_costs or 0),
        "total": float(summary.total_cost)
    }
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    return CostSummary(
        total_cost=float(summary.total_cost),
        service_breakdown=service_breakdown,
        period_days=days,
        start_date=start_date,
        end_date=end_date
    )


@router.get("/daily", response_model=List[DailyCost])
async def get_daily_costs(
    days: int = Query(7, ge=1, le=30, description="Number of days to retrieve"),
    current_user: User = Depends(get_current_user)
):
    """Get daily cost breakdown"""
    tracker = get_cost_tracker()
    
    # Get daily costs for the period
    daily_costs = []
    
    for i in range(days):
        date = datetime.utcnow().date() - timedelta(days=i)
        
        # Get costs for this day
        day_summary = await tracker.get_cost_summary(
            start_date=date,
            end_date=date + timedelta(days=1)
        )
        
        daily_costs.append(DailyCost(
            date=date.isoformat(),
            total_cost=float(day_summary.total_cost),
            service_costs={
                "aws_cost_explorer": float(day_summary.aws_costs),
                "spotify_api": float(day_summary.spotify_costs or 0),
                "transcription": float(day_summary.transcription_costs or 0),
                "llm_api": float(day_summary.llm_costs or 0)
            },
            api_calls=day_summary.total_api_calls
        ))
    
    return daily_costs


@router.get("/by-user", response_model=List[UserCost])
async def get_costs_by_user(
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    current_user: User = Depends(get_current_user)
):
    """Get cost breakdown by user (admin only)"""
    
    # For now, return only current user's costs
    # In production, add admin check and return all users
    tracker = get_cost_tracker()
    
    user_costs = await tracker.get_cost_by_user(days=days)
    
    return [
        UserCost(
            user_id=user_id,
            email=None,  # Would need to join with users table
            total_cost=float(costs['total_cost']),
            service_breakdown=costs['service_breakdown'],
            api_calls=costs['total_api_calls']
        )
        for user_id, costs in user_costs.items()
        if user_id == str(current_user.id) or current_user.is_superuser
    ]


@router.get("/budget/status", response_model=BudgetStatus)
async def get_budget_status(
    current_user: User = Depends(get_current_user)
):
    """Get current budget status"""
    tracker = get_cost_tracker()
    
    # Get current spending
    daily_spent = await tracker.get_real_daily_spend()
    weekly_spent = await tracker.get_real_weekly_spend()
    monthly_spent = await tracker.get_real_monthly_spend()
    
    # Get limits from config
    config = tracker.config
    
    # Calculate remaining
    daily_remaining = max(0, float(config.daily_budget_limit) - float(daily_spent))
    weekly_remaining = max(0, float(config.weekly_budget_limit) - float(weekly_spent))
    monthly_remaining = max(0, float(config.monthly_budget_limit) - float(monthly_spent))
    
    # Check if at risk (>80% of any limit)
    at_risk = (
        daily_spent > config.daily_budget_limit * 0.8 or
        weekly_spent > config.weekly_budget_limit * 0.8 or
        monthly_spent > config.monthly_budget_limit * 0.8
    )
    
    return BudgetStatus(
        daily_spent=float(daily_spent),
        daily_limit=float(config.daily_budget_limit),
        daily_remaining=daily_remaining,
        weekly_spent=float(weekly_spent),
        weekly_limit=float(config.weekly_budget_limit),
        weekly_remaining=weekly_remaining,
        monthly_spent=float(monthly_spent),
        monthly_limit=float(config.monthly_budget_limit),
        monthly_remaining=monthly_remaining,
        at_risk=at_risk
    )


@router.post("/simulate")
async def simulate_operation_cost(
    operation: str = Query(..., description="Operation name"),
    estimated_cost: float = Query(..., description="Estimated cost in dollars"),
    current_user: User = Depends(get_current_user)
):
    """Simulate if an operation would exceed budget"""
    tracker = get_cost_tracker()
    
    # Check if operation would exceed budget
    can_proceed = await tracker.check_budget_before_operation(
        str(current_user.id),
        operation,
        estimated_cost
    )
    
    # Get current spending for context
    daily_spent = await tracker.get_real_daily_spend()
    weekly_spent = await tracker.get_real_weekly_spend()
    monthly_spent = await tracker.get_real_monthly_spend()
    
    return {
        "can_proceed": can_proceed,
        "operation": operation,
        "estimated_cost": estimated_cost,
        "current_spending": {
            "daily": float(daily_spent),
            "weekly": float(weekly_spent),
            "monthly": float(monthly_spent)
        },
        "would_exceed": {
            "daily": float(daily_spent) + estimated_cost > float(tracker.config.daily_budget_limit),
            "weekly": float(weekly_spent) + estimated_cost > float(tracker.config.weekly_budget_limit),
            "monthly": float(monthly_spent) + estimated_cost > float(tracker.config.monthly_budget_limit)
        }
    }
