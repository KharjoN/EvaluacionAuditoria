.PHONY: init install run

init:
	poetry add fastapi uvicorn SQLAlchemy pydantic python-dotenv asyncgp python-jose[cryptography] passlib[bcrypt] python-multipart

install:
	poetry install --no-root
run:
	poetry run uvicorn src.backend.main:app --reload --host 0.0.0.0 --port 8000
docker-up:
	docker-compose up --build
docker-down:
	docker-compose down
docker-restart:
	docker-compose restart
docker-clean:
	docker-compose down -v