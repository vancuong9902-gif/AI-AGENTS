up:
	docker compose up -d
	@echo "✅ API: http://localhost:8000 | Frontend: http://localhost:5173"

down:
	docker compose down

test:
	cd backend && python -m pytest -q --tb=short
