FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml poetry.lock* /app/
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi
COPY . /app
ENV PORT=8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--proxy-headers","--forwarded-allow-ips","*"]
