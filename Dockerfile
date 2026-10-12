FROM python:3.12-slim
WORKDIR /srv/app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY run.py ./run.py
EXPOSE 8080
CMD ["python","-m","app.entrypoint"]
