"""
Configuration management for multi-user podcast Q&A system.
Handles AWS credentials, cost limits, and user isolation settings.
"""

import os
from decimal import Decimal
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings with validation for real AWS integration."""
    
    # AWS Configuration - REQUIRED FOR REAL COST TRACKING
    aws_access_key_id: str = Field(..., description="AWS Access Key ID")
    aws_secret_access_key: str = Field(..., description="AWS Secret Access Key")
    aws_region: str = Field(default="us-east-1", description="AWS Region")
    aws_account_id: str = Field(..., description="AWS Account ID")
    
    # Cost Monitoring Configuration - CRITICAL FOR MULTI-USER SYSTEM
    daily_budget_limit: Decimal = Field(default=Decimal("5.00"), description="Daily spending limit in USD")
    weekly_budget_limit: Decimal = Field(default=Decimal("25.00"), description="Weekly spending limit in USD")
    monthly_budget_limit: Decimal = Field(default=Decimal("100.00"), description="Monthly spending limit in USD")
    emergency_stop_budget: Decimal = Field(default=Decimal("50.00"), description="Emergency stop threshold in USD")
    cost_alert_email: str = Field(..., description="Email for cost alerts")
    
    # Database Configuration
    database_url: str = Field(..., description="PostgreSQL connection string")
    database_url_test: Optional[str] = Field(None, description="Test database connection string")
    
    # Application Security
    secret_key: str = Field(..., description="JWT secret key")
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=30, description="JWT expiration time")
    
    # Environment
    environment: str = Field(default="development", description="Application environment")
    
    # Email Configuration (SMTP - Free!)
    smtp_host: str = Field(default="smtp.gmail.com", description="SMTP server host")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_username: str = Field(..., description="SMTP username (email address)")
    smtp_password: str = Field(..., description="SMTP password (app password for Gmail)")
    from_email: str = Field(..., description="From email address for notifications")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Cost Tracking Settings
    enable_cost_tracking: bool = Field(default=True, description="Enable real-time cost tracking")
    cost_check_interval_minutes: int = Field(default=60, description="Cost check interval in minutes")
    
    @validator('daily_budget_limit', 'weekly_budget_limit', 'monthly_budget_limit', 'emergency_stop_budget')
    def validate_budget_limits(cls, v):
        """Ensure budget limits are positive."""
        if v <= 0:
            raise ValueError("Budget limits must be positive")
        return v
    
    @validator('aws_account_id')
    def validate_aws_account_id(cls, v):
        """Validate AWS account ID format."""
        if not v.isdigit() or len(v) != 12:
            raise ValueError("AWS Account ID must be a 12-digit number")
        return v
    
    class Config:
        env_file = "config.env"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings 