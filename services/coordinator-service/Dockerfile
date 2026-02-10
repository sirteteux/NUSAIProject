FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Expose port (matches docker-compose PORT environment variable)
EXPOSE 8007

# Run the application using main.py which reads PORT env var
CMD ["python", "src/main.py"]