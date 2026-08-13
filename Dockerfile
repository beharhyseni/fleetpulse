# build stage - none of it ships
FROM python:3.12-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# runtime stage - what actually ships
FROM python:3.12-slim
RUN useradd -m -u 10001 appuser
WORKDIR /app
COPY --from=build /install /usr/local
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
