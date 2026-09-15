FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY agent_manifest.json ./agent_manifest.json
EXPOSE 8000
ENV GRIOT_DB_PATH=/app/griot.db
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
