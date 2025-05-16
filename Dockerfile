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
COPY tests/ /app/tests/

ENV PYTHONPATH=/app

# om tests te kunnen draaien
ENV SENDGRID_API_KEY=dummy_key
ENV RABBITMQ_HOST=localhost
ENV RABBITMQ_PORT=5672
ENV RABBITMQ_USER=user
ENV RABBITMQ_PASSWORD=pass
ENV QRCODE_TEMPLATE_ID=qrcode_tpl
ENV FACTURATIE_TEMPLATE_ID=facturatie_tpl
ENV CONTROLROOM_TEMPLATE_ID=control_tpl
ENV FRONTEND_TEMPLATE_ID=frontend_tpl
# Start mail service als standaard
CMD ["python", "-u", "mail_service.py"]
