.PHONY: init install run

init:
	poetry add fastapi uvicorn SQLAlchemy pydantic python-dotenv asyncgp

install:
	poetry install --no-root
run:
	poetry run uvicorn src.backend.main:app --reload --host 0.0.0.0 --port 8002