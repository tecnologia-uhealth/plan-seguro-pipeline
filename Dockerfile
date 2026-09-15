FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala Chromium + todas las librerías de sistema que necesita Playwright
RUN playwright install --with-deps chromium

COPY . .

ENV PORT=5002
EXPOSE 5002

CMD ["python3", "webhook_plan_seguro.py"]
