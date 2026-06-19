import re

with open("docker-compose.yml", "r") as f:
    text = f.read()

text = text.replace(
    "- DATABASE_URL=postgresql://model_user:model_pass@model-postgres:5432/model_db",
    "- DATABASE_URL=postgresql://postgres:${POSTGRES_PASSWORD:-postgres}@postgres:5432/${POSTGRES_DB:-thingsboard}"
)

with open("docker-compose.yml", "w") as f:
    f.write(text)
