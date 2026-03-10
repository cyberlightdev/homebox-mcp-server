FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir .

ENV PYTHONPATH=/app/src

RUN python -c "import homebox_mcp; print('OK:', homebox_mcp.__file__)"

EXPOSE 8100

CMD ["python", "-m", "homebox_mcp.server"]
