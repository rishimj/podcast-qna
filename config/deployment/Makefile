.PHONY: help install install-dev test test-unit test-integration test-coverage lint format security clean docker-build docker-run pre-commit setup-hooks ci-local

# Default target
help: ## Show this help message
	@echo "🚀 Podcast Q&A Development Commands"
	@echo "=================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Installation
install: ## Install production dependencies
	pip install -r requirements.txt

install-dev: ## Install development dependencies
	pip install -r requirements.txt
	pip install pytest pytest-asyncio pytest-cov pytest-mock black isort flake8 mypy bandit safety moto[all] pre-commit

# Testing
test: ## Run all tests
	@echo "🧪 Running all tests..."
	python -m pytest tests/ -v --tb=short

test-unit: ## Run unit tests only
	@echo "🧪 Running unit tests..."
	python -m pytest tests/ -v --tb=short -m "not integration"

test-integration: ## Run integration tests only
	@echo "🔗 Running integration tests..."
	python -m pytest tests/test_minimal_aws.py -v --tb=short

test-coverage: ## Run tests with coverage report
	@echo "📊 Running tests with coverage..."
	python -m pytest tests/ --cov=src --cov-report=html --cov-report=term-missing --cov-report=xml

test-real: ## Run tests with real AWS (requires credentials)
	@echo "☁️ Running tests with real AWS..."
	python -m pytest tests/test_real_cost_tracking.py -v --tb=short

# Code Quality
lint: ## Run all linting checks
	@echo "🧹 Running linting checks..."
	flake8 src/ tests/ *.py --max-line-length=100 --ignore=E203,W503
	mypy src/ --ignore-missing-imports
	@echo "✅ Linting completed"

format: ## Format code with black and isort
	@echo "🎨 Formatting code..."
	black src/ tests/ *.py --line-length=100
	isort src/ tests/ *.py --profile=black --line-length=100
	@echo "✅ Code formatted"

format-check: ## Check code formatting without making changes
	@echo "🔍 Checking code formatting..."
	black --check --diff src/ tests/ *.py --line-length=100
	isort --check-only --diff src/ tests/ *.py --profile=black --line-length=100

security: ## Run security scans
	@echo "🔒 Running security scans..."
	bandit -r src/ --severity-level medium
	safety check
	@echo "✅ Security scan completed"

# Development
clean: ## Clean up build artifacts and cache
	@echo "🧹 Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf dist/
	rm -rf build/
	@echo "✅ Cleanup completed"

# Docker
docker-build: ## Build Docker image
	@echo "🐳 Building Docker image..."
	docker build -t podcast-qa:latest .
	@echo "✅ Docker image built"

docker-run: ## Run Docker container
	@echo "🐳 Running Docker container..."
	docker run --rm -it podcast-qa:latest

docker-test: ## Test Docker container
	@echo "🧪 Testing Docker container..."
	docker run --rm podcast-qa:latest python -c "import src.config; print('✅ Container test passed')"

# Pre-commit
setup-hooks: ## Set up pre-commit hooks
	@echo "🔧 Setting up pre-commit hooks..."
	pre-commit install
	pre-commit install --hook-type commit-msg
	@echo "✅ Pre-commit hooks installed"

pre-commit: ## Run pre-commit on all files
	@echo "🔍 Running pre-commit checks..."
	pre-commit run --all-files

# CI/CD Simulation
ci-local: ## Run full CI pipeline locally
	@echo "🚀 Running CI pipeline locally..."
	@echo "1️⃣ Security scan..."
	$(MAKE) security
	@echo "2️⃣ Code formatting check..."
	$(MAKE) format-check
	@echo "3️⃣ Linting..."
	$(MAKE) lint
	@echo "4️⃣ Unit tests..."
	$(MAKE) test-unit
	@echo "5️⃣ Integration tests..."
	$(MAKE) test-integration
	@echo "6️⃣ Coverage report..."
	$(MAKE) test-coverage
	@echo "7️⃣ Docker build..."
	$(MAKE) docker-build
	@echo "8️⃣ Docker test..."
	$(MAKE) docker-test
	@echo "🎉 Local CI pipeline completed successfully!"

# Daily reports
daily-report: ## Run daily cost report manually
	@echo "📊 Running daily cost report..."
	python daily_cost_report.py

setup-cron: ## Set up daily cost report cron job
	@echo "⏰ Setting up daily cost reports..."
	./setup_daily_reports.sh

# Development workflow
dev-setup: install-dev setup-hooks ## Complete development environment setup
	@echo "🎯 Development environment ready!"

dev-check: format lint test ## Quick development check (format, lint, test)
	@echo "✅ Development check completed"

# Release preparation
release-check: ci-local ## Full release readiness check
	@echo "🚀 Release readiness check completed"

# AWS Cost Tracking
cost-check: ## Check current AWS costs
	@python scripts/check_costs.py

api-costs: ## Check Cost Explorer API usage and costs
	@echo "🔍 Checking Cost Explorer API usage..."
	@python -c "from src.cost_aware_tracker import get_cost_aware_tracker; import json; print(json.dumps(get_cost_aware_tracker().get_api_cost_summary(), indent=2))"

# Help
list: help ## Alias for help 