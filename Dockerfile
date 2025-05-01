FROM python:latest
WORKDIR /usr/local/bin
COPY mail_service.py .
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python","-u","mail_service.py"]
