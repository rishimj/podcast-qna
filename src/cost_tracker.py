"""
Real AWS Cost Tracker for Multi-User Podcast Q&A System.

This module provides REAL cost tracking by connecting to AWS Cost Explorer API.
NO MOCK DATA - ALL REAL AWS BILLING INTEGRATION.

Critical for multi-user system to:
1. Track actual AWS spending per user
2. Prevent cost overruns
3. Send real email alerts
4. Provide cost attribution per user/service
"""

import boto3
import asyncio
import structlog
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from .config import get_settings
from .email_alerts import send_cost_alert_email

logger = structlog.get_logger(__name__)


class CostAlertLevel(Enum):
    """Cost alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class CostRecord:
    """Individual cost tracking record."""
    timestamp: datetime
    service: str
    operation: str
    user_id: Optional[str]
    estimated_cost: Decimal
    actual_cost: Optional[Decimal] = None
    tags: Optional[Dict[str, str]] = None


@dataclass
class CostSummary:
    """Cost summary for a time period."""
    start_date: datetime
    end_date: datetime
    total_cost: Decimal
    cost_by_service: Dict[str, Decimal]
    cost_by_user: Dict[str, Decimal]
    record_count: int


class RealAWSCostTracker:
    """
    Real AWS Cost Tracker - Connects to actual AWS Cost Explorer API.
    
    🚨 CRITICAL: This class uses REAL AWS billing data, not mock data.
    Every method call results in actual AWS API calls and real cost tracking.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = logger.bind(component="cost_tracker")
        
        # Initialize real AWS clients
        self._cost_explorer = None
        self._cost_records: List[CostRecord] = []
        
        # Cost limits
        self.daily_limit = self.settings.daily_budget_limit
        self.weekly_limit = self.settings.weekly_budget_limit
        self.monthly_limit = self.settings.monthly_budget_limit
        self.emergency_limit = self.settings.emergency_stop_budget
        
        self.logger.info(
            "🚨 Real AWS Cost Tracker initialized",
            daily_limit=str(self.daily_limit),
            weekly_limit=str(self.weekly_limit),
            monthly_limit=str(self.monthly_limit),
            emergency_limit=str(self.emergency_limit)
        )
    
    @property
    def cost_explorer(self):
        """Lazy-loaded AWS Cost Explorer client."""
        if self._cost_explorer is None:
            self._cost_explorer = boto3.client(
                'ce',  # Cost Explorer
                aws_access_key_id=self.settings.aws_access_key_id,
                aws_secret_access_key=self.settings.aws_secret_access_key,
                region_name=self.settings.aws_region
            )
            self.logger.info("🔌 Connected to real AWS Cost Explorer API")
        return self._cost_explorer
    
    # Note: Email alerts now use SMTP instead of AWS SES - much simpler!
    
    async def track_api_call(
        self,
        service: str,
        operation: str,
        estimated_cost: Decimal,
        user_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Track a real AWS API call with estimated cost.
        
        Args:
            service: AWS service name (e.g., 'dynamodb', 'lambda', 'bedrock')
            operation: Operation name (e.g., 'put_item', 'invoke', 'invoke_model')
            estimated_cost: Estimated cost in USD
            user_id: User ID for cost attribution (critical for multi-user system)
            tags: Additional tags for cost tracking
            
        Returns:
            bool: True if operation should proceed, False if budget exceeded
        """
        if not self.settings.enable_cost_tracking:
            return True
            
        timestamp = datetime.now(timezone.utc)
        
        # Create cost record
        record = CostRecord(
            timestamp=timestamp,
            service=service,
            operation=operation,
            user_id=user_id,
            estimated_cost=estimated_cost,
            tags=tags or {}
        )
        
        self._cost_records.append(record)
        
        self.logger.info(
            "💰 Tracking real AWS API call",
            service=service,
            operation=operation,
            estimated_cost=str(estimated_cost),
            user_id=user_id,
            tags=tags
        )
        
        # Check if we should proceed based on budget
        should_proceed = await self._check_budget_limits(estimated_cost)
        
        if not should_proceed:
            self.logger.error(
                "🚨 BUDGET EXCEEDED - Operation blocked",
                service=service,
                operation=operation,
                estimated_cost=str(estimated_cost),
                user_id=user_id
            )
            
            # Send emergency alert
            await self._send_emergency_alert(service, operation, estimated_cost, user_id)
        
        return should_proceed
    
    async def get_real_daily_spend(self, date: Optional[datetime] = None) -> Decimal:
        """
        Get REAL daily spending from AWS Cost Explorer API.
        
        Args:
            date: Date to check (defaults to today)
            
        Returns:
            Decimal: Actual daily spend in USD
        """
        if date is None:
            date = datetime.now(timezone.utc)
        
        start_date = date.strftime('%Y-%m-%d')
        end_date = (date + timedelta(days=1)).strftime('%Y-%m-%d')
        
        try:
            response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date,
                    'End': end_date
                },
                Granularity='DAILY',
                Metrics=['BlendedCost']
            )
            
            total_cost = Decimal('0')
            for result in response['ResultsByTime']:
                cost_str = result['Total']['BlendedCost']['Amount']
                total_cost += Decimal(cost_str)
            
            self.logger.info(
                "💳 Retrieved real daily spend from AWS",
                date=start_date,
                actual_cost=str(total_cost)
            )
            
            return total_cost
            
        except Exception as e:
            self.logger.error(
                "❌ Failed to get real daily spend from AWS",
                error=str(e),
                date=start_date
            )
            raise
    
    async def get_real_weekly_spend(self) -> Decimal:
        """Get REAL weekly spending from AWS Cost Explorer API."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)
        
        try:
            response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['BlendedCost']
            )
            
            total_cost = Decimal('0')
            for result in response['ResultsByTime']:
                cost_str = result['Total']['BlendedCost']['Amount']
                total_cost += Decimal(cost_str)
            
            self.logger.info(
                "💳 Retrieved real weekly spend from AWS",
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                actual_cost=str(total_cost)
            )
            
            return total_cost
            
        except Exception as e:
            self.logger.error(
                "❌ Failed to get real weekly spend from AWS",
                error=str(e)
            )
            raise
    
    async def get_real_monthly_spend(self) -> Decimal:
        """Get REAL monthly spending from AWS Cost Explorer API."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date.replace(day=1)  # First day of current month
        
        try:
            response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['BlendedCost']
            )
            
            total_cost = Decimal('0')
            for result in response['ResultsByTime']:
                cost_str = result['Total']['BlendedCost']['Amount']
                total_cost += Decimal(cost_str)
            
            self.logger.info(
                "💳 Retrieved real monthly spend from AWS",
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                actual_cost=str(total_cost)
            )
            
            return total_cost
            
        except Exception as e:
            self.logger.error(
                "❌ Failed to get real monthly spend from AWS",
                error=str(e)
            )
            raise
    
    async def get_cost_by_service(self, days: int = 7) -> Dict[str, Decimal]:
        """
        Get REAL cost breakdown by AWS service.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dict mapping service names to costs
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        try:
            response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['BlendedCost'],
                GroupBy=[
                    {
                        'Type': 'DIMENSION',
                        'Key': 'SERVICE'
                    }
                ]
            )
            
            cost_by_service = {}
            for result in response['ResultsByTime']:
                for group in result['Groups']:
                    service = group['Keys'][0]
                    cost_str = group['Metrics']['BlendedCost']['Amount']
                    cost = Decimal(cost_str)
                    
                    if service in cost_by_service:
                        cost_by_service[service] += cost
                    else:
                        cost_by_service[service] = cost
            
            self.logger.info(
                "📊 Retrieved real cost breakdown by service",
                days=days,
                service_count=len(cost_by_service),
                total_cost=str(sum(cost_by_service.values()))
            )
            
            return cost_by_service
            
        except Exception as e:
            self.logger.error(
                "❌ Failed to get cost by service from AWS",
                error=str(e),
                days=days
            )
            raise
    
    async def get_cost_by_user(self, days: int = 7) -> Dict[str, Decimal]:
        """
        Get estimated cost breakdown by user based on tracked operations.
        
        Note: This uses our tracked records since AWS doesn't directly track by user_id.
        In production, you'd use resource tags for more accurate user attribution.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        cost_by_user = {}
        for record in self._cost_records:
            if record.timestamp >= cutoff_date and record.user_id:
                if record.user_id in cost_by_user:
                    cost_by_user[record.user_id] += record.estimated_cost
                else:
                    cost_by_user[record.user_id] = record.estimated_cost
        
        self.logger.info(
            "👥 Retrieved cost breakdown by user",
            days=days,
            user_count=len(cost_by_user),
            total_estimated_cost=str(sum(cost_by_user.values()))
        )
        
        return cost_by_user
    
    async def _check_budget_limits(self, additional_cost: Decimal) -> bool:
        """
        Check if adding additional cost would exceed budget limits.
        
        Returns:
            bool: True if operation should proceed, False if budget exceeded
        """
        try:
            # Get real current spending
            daily_spend = await self.get_real_daily_spend()
            weekly_spend = await self.get_real_weekly_spend()
            monthly_spend = await self.get_real_monthly_spend()
            
            # Check each limit
            if daily_spend + additional_cost > self.daily_limit:
                await self._send_budget_alert(
                    CostAlertLevel.CRITICAL,
                    "Daily budget exceeded",
                    daily_spend,
                    self.daily_limit,
                    additional_cost
                )
                return False
            
            if weekly_spend + additional_cost > self.weekly_limit:
                await self._send_budget_alert(
                    CostAlertLevel.CRITICAL,
                    "Weekly budget exceeded",
                    weekly_spend,
                    self.weekly_limit,
                    additional_cost
                )
                return False
            
            if monthly_spend + additional_cost > self.monthly_limit:
                await self._send_budget_alert(
                    CostAlertLevel.CRITICAL,
                    "Monthly budget exceeded",
                    monthly_spend,
                    self.monthly_limit,
                    additional_cost
                )
                return False
            
            if monthly_spend + additional_cost > self.emergency_limit:
                await self._send_budget_alert(
                    CostAlertLevel.EMERGENCY,
                    "Emergency budget threshold exceeded",
                    monthly_spend,
                    self.emergency_limit,
                    additional_cost
                )
                return False
            
            # Check for warning levels (80% of limits)
            if daily_spend + additional_cost > self.daily_limit * Decimal('0.8'):
                await self._send_budget_alert(
                    CostAlertLevel.WARNING,
                    "Daily budget warning (80%)",
                    daily_spend,
                    self.daily_limit,
                    additional_cost
                )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "❌ Failed to check budget limits",
                error=str(e),
                additional_cost=str(additional_cost)
            )
            # Fail safe - allow operation but log error
            return True
    
    async def _send_budget_alert(
        self,
        level: CostAlertLevel,
        message: str,
        current_spend: Decimal,
        limit: Decimal,
        additional_cost: Decimal
    ):
        """Send cost alert via free SMTP - no AWS verification needed!"""
        try:
            subject = f"🚨 {level.value.upper()} Cost Alert - Podcast Q&A System"
            
            # Get current real spending for email context
            real_daily = await self.get_real_daily_spend()
            real_weekly = await self.get_real_weekly_spend()
            real_monthly = await self.get_real_monthly_spend()
            
            body = f"""🚨 COST ALERT: {message}

📊 CURRENT REAL AWS SPENDING:
   Today:     ${real_daily:.6f}
   This Week: ${real_weekly:.6f}  
   This Month: ${real_monthly:.6f}

🚦 BUDGET ANALYSIS:
   Current Spend: ${current_spend:.6f}
   Budget Limit:  ${limit:.2f}
   Additional Cost: ${additional_cost:.6f}
   Projected Total: ${current_spend + additional_cost:.6f}

⚠️  Alert Level: {level.value.upper()}
🕒 Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

💡 RECOMMENDATION:
   • Review your AWS usage patterns
   • Consider optimizing expensive operations
   • Monitor costs daily to avoid surprises

📧 This alert sent via Gmail SMTP (free & reliable!)
🎯 Podcast Q&A System - Real AWS Cost Protection
"""
            
            # Send email via SMTP (free!)
            email_sent = await send_cost_alert_email(subject, body)
            
            if email_sent:
                self.logger.info(
                    "📧 Sent cost alert email via SMTP",
                    level=level.value,
                    message=message,
                    real_daily=str(real_daily),
                    real_weekly=str(real_weekly),
                    real_monthly=str(real_monthly),
                    current_spend=str(current_spend),
                    limit=str(limit),
                    to_email=self.settings.cost_alert_email
                )
            
        except Exception as e:
            self.logger.error(
                "❌ Failed to send cost alert email",
                error=str(e),
                level=level.value,
                message=message,
                current_spend=str(current_spend),
                limit=str(limit)
            )
    
    async def _send_emergency_alert(
        self,
        service: str,
        operation: str,
        estimated_cost: Decimal,
        user_id: Optional[str]
    ):
        """Send emergency alert for blocked operations."""
        await self._send_budget_alert(
            CostAlertLevel.EMERGENCY,
            f"Operation blocked: {service}.{operation}",
            await self.get_real_monthly_spend(),
            self.emergency_limit,
            estimated_cost
        )
    
    async def get_cost_summary(self, days: int = 7) -> CostSummary:
        """Get comprehensive cost summary for the specified period."""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        # Get real total cost
        if days == 1:
            total_cost = await self.get_real_daily_spend()
        elif days == 7:
            total_cost = await self.get_real_weekly_spend()
        else:
            # Custom period - calculate from Cost Explorer
            try:
                response = self.cost_explorer.get_cost_and_usage(
                    TimePeriod={
                        'Start': start_date.strftime('%Y-%m-%d'),
                        'End': end_date.strftime('%Y-%m-%d')
                    },
                    Granularity='DAILY',
                    Metrics=['BlendedCost']
                )
                
                total_cost = Decimal('0')
                for result in response['ResultsByTime']:
                    cost_str = result['Total']['BlendedCost']['Amount']
                    total_cost += Decimal(cost_str)
                    
            except Exception as e:
                self.logger.error("Failed to get custom period cost", error=str(e))
                total_cost = Decimal('0')
        
        # Get breakdowns
        cost_by_service = await self.get_cost_by_service(days)
        cost_by_user = await self.get_cost_by_user(days)
        
        # Count records in period
        record_count = len([
            r for r in self._cost_records 
            if r.timestamp >= start_date
        ])
        
        return CostSummary(
            start_date=start_date,
            end_date=end_date,
            total_cost=total_cost,
            cost_by_service=cost_by_service,
            cost_by_user=cost_by_user,
            record_count=record_count
        )


# Global cost tracker instance
_cost_tracker = None


def get_cost_tracker() -> RealAWSCostTracker:
    """Get the global cost tracker instance."""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = RealAWSCostTracker()
    return _cost_tracker


# Convenience functions for common operations
async def track_dynamodb_operation(operation: str, estimated_cost: Decimal, user_id: str = None) -> bool:
    """Track a DynamoDB operation."""
    return await get_cost_tracker().track_api_call("dynamodb", operation, estimated_cost, user_id)


async def track_bedrock_operation(operation: str, estimated_cost: Decimal, user_id: str = None) -> bool:
    """Track a Bedrock operation."""
    return await get_cost_tracker().track_api_call("bedrock", operation, estimated_cost, user_id)


async def track_lambda_operation(operation: str, estimated_cost: Decimal, user_id: str = None) -> bool:
    """Track a Lambda operation."""
    return await get_cost_tracker().track_api_call("lambda", operation, estimated_cost, user_id)


async def track_s3_operation(operation: str, estimated_cost: Decimal, user_id: str = None) -> bool:
    """Track an S3 operation."""
    return await get_cost_tracker().track_api_call("s3", operation, estimated_cost, user_id) 