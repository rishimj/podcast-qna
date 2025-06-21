#!/usr/bin/env python3
"""
Cost-Aware AWS Cost Tracker
Limits Cost Explorer API calls to prevent runaway costs.
"""

import asyncio
import os
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional
import structlog

from .cost_tracker import RealAWSCostTracker
from .config import get_settings

logger = structlog.get_logger()

class CostAwareCostTracker:
    """
    Wrapper around CostTracker that limits API calls to prevent high costs.
    
    Cost Explorer API costs $0.01 per request, so we need to be careful!
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.tracker = RealAWSCostTracker()
        self.cache_file = "logs/cost_cache.json"
        self.max_daily_api_calls = 10  # Limit to $0.10/day in API costs
        self.cache_duration_hours = 6  # Cache results for 6 hours
        
    def _get_cache_key(self, operation: str, **kwargs) -> str:
        """Generate cache key for operation."""
        key_parts = [operation]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        return "|".join(key_parts)
    
    def _load_cache(self) -> Dict[str, Any]:
        """Load cached API results."""
        if not os.path.exists(self.cache_file):
            return {}
        
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_cache(self, cache: Dict[str, Any]):
        """Save cache to file."""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w') as f:
            json.dump(cache, f, indent=2, default=str)
    
    def _is_cache_valid(self, timestamp_str: str) -> bool:
        """Check if cache entry is still valid."""
        try:
            cached_time = datetime.fromisoformat(timestamp_str)
            current_time = datetime.now(timezone.utc)
            return (current_time - cached_time).total_seconds() < (self.cache_duration_hours * 3600)
        except:
            return False
    
    def _count_todays_api_calls(self) -> int:
        """Count how many API calls made today."""
        cache = self._load_cache()
        today = datetime.now(timezone.utc).date().isoformat()
        
        count = 0
        for key, entry in cache.items():
            if isinstance(entry, dict) and 'timestamp' in entry:
                try:
                    entry_date = datetime.fromisoformat(entry['timestamp']).date().isoformat()
                    if entry_date == today:
                        count += 1
                except:
                    continue
        return count
    
    async def _cached_api_call(self, operation: str, api_func, **kwargs) -> Any:
        """Make API call with caching and rate limiting."""
        cache_key = self._get_cache_key(operation, **kwargs)
        cache = self._load_cache()
        
        # Check cache first
        if cache_key in cache:
            entry = cache[cache_key]
            if isinstance(entry, dict) and 'timestamp' in entry:
                if self._is_cache_valid(entry['timestamp']):
                    logger.info(
                        "📋 Using cached result",
                        operation=operation,
                        cached_at=entry['timestamp']
                    )
                    result = entry['result']
                    # Convert strings back to Decimal for spend operations
                    if 'spend' in operation and isinstance(result, str):
                        result = Decimal(result)
                    elif isinstance(result, dict):
                        # Convert dict values back to Decimal
                        result = {k: Decimal(v) if isinstance(v, str) and v.replace('.', '').replace('-', '').isdigit() else v 
                                for k, v in result.items()}
                    return result
        
        # Check daily API call limit
        todays_calls = self._count_todays_api_calls()
        if todays_calls >= self.max_daily_api_calls:
            logger.warning(
                "🚨 Daily API call limit reached",
                calls_made=todays_calls,
                limit=self.max_daily_api_calls,
                estimated_cost=todays_calls * 0.01
            )
            
            # Return cached result if available, even if expired
            if cache_key in cache and 'result' in cache[cache_key]:
                logger.info("📋 Using expired cache due to API limit")
                result = cache[cache_key]['result']
                # Convert strings back to Decimal for spend operations
                if 'spend' in operation and isinstance(result, str):
                    result = Decimal(result)
                elif isinstance(result, dict):
                    # Convert dict values back to Decimal
                    result = {k: Decimal(v) if isinstance(v, str) and v.replace('.', '').replace('-', '').isdigit() else v 
                            for k, v in result.items()}
                return result
            
            # If no cache, return zero/empty to avoid costs
            logger.warning("⚠️ No cache available, returning safe default")
            if 'spend' in operation:
                return Decimal('0')
            else:
                return {}
        
        # Make the actual API call
        logger.info(
            "📞 Making Cost Explorer API call",
            operation=operation,
            todays_calls=todays_calls + 1,
            estimated_cost=(todays_calls + 1) * 0.01
        )
        
        result = await api_func(**kwargs)
        
        # Cache the result
        cache[cache_key] = {
            'result': result,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        self._save_cache(cache)
        
        return result
    
    async def get_real_daily_spend(self) -> Decimal:
        """Get daily spend with caching."""
        return await self._cached_api_call(
            "daily_spend",
            self.tracker.get_real_daily_spend
        )
    
    async def get_real_weekly_spend(self) -> Decimal:
        """Get weekly spend with caching."""
        return await self._cached_api_call(
            "weekly_spend", 
            self.tracker.get_real_weekly_spend
        )
    
    async def get_real_monthly_spend(self) -> Decimal:
        """Get monthly spend with caching."""
        return await self._cached_api_call(
            "monthly_spend",
            self.tracker.get_real_monthly_spend
        )
    
    async def get_cost_by_service(self, days: int = 7) -> Dict[str, Decimal]:
        """Get service costs with caching."""
        return await self._cached_api_call(
            "service_costs",
            self.tracker.get_cost_by_service,
            days=days
        )
    
    def get_api_cost_summary(self) -> Dict[str, Any]:
        """Get summary of API costs incurred."""
        cache = self._load_cache()
        today = datetime.now(timezone.utc).date().isoformat()
        
        todays_calls = self._count_todays_api_calls()
        estimated_cost = todays_calls * 0.01
        
        return {
            'todays_api_calls': todays_calls,
            'estimated_api_cost': f"${estimated_cost:.2f}",
            'daily_limit': self.max_daily_api_calls,
            'remaining_calls': max(0, self.max_daily_api_calls - todays_calls),
            'cache_entries': len(cache),
            'cache_file': self.cache_file
        }

def get_cost_aware_tracker() -> CostAwareCostTracker:
    """Get cost-aware tracker instance."""
    return CostAwareCostTracker() 