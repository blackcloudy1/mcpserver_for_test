FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

RUN groupadd --system lab && useradd --system --gid lab --home /workspace lab

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY security_lab ./security_lab
COPY tests ./tests
COPY fixtures ./fixtures

USER lab

CMD ["uvicorn", "security_lab.app:app", "--host", "0.0.0.0", "--port", "8080"]
