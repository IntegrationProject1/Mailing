FROM python:3.10-slim

WORKDIR /app

# Kopieer algemene dependencies
COPY requirements.txt /app/

# Installeer requirements
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer beide scripts
COPY mail_service.py /app/
COPY publisher/heartbeat_publisher.py /app/
COPY publisher/heartbeat.xsd /app/

# Start mail service als standaard
CMD ["python", "-u", "mail_service.py"]
