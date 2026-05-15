FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

EXPOSE 5001
CMD ["gunicorn", "-w", "1", "--threads", "8", "-b", "0.0.0.0:5001", "--timeout", "120", "app:app"]
