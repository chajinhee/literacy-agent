FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py translation_agent.py coaching_agent.py ./
COPY static ./static

# Cloud Run은 PORT 환경변수로 리스닝 포트를 지정함
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
