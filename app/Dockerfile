FROM python:3.13-alpine
RUN apk add --no-cache ttyd bash
WORKDIR /opt/ha-context
COPY . /opt/ha-context/app
RUN pip install --no-cache-dir -r app/requirements.txt -r app/requirements-haos.txt
ENV PYTHONPATH=/opt/ha-context/app PYTHONDONTWRITEBYTECODE=1 HA_CONTEXT_ADDON=1
CMD ["python3", "-m", "hacontext.gateway"]
