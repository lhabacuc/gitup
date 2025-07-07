FROM python:3.12-slim

WORKDIR /app

COPY gitup.py .

RUN pip install --no-cache-dir pyinstaller requests

CMD ["pyinstaller", "--onefile", "--name", "gitup", "--hidden-import", "requests", "gitup.py"]
