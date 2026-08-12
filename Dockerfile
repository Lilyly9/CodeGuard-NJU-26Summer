FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY webui/ webui/

EXPOSE 5000

CMD ["python", "webui/app.py"]