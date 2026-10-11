FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
# 镜像源可用 build-arg 覆盖：阿里云在部分网络下会卡在单文件下载上（2026-10-11 实测
# curl_cffi 卡 150s+，换腾讯镜像同文件 5s），默认值保持不变。
ARG PIP_INDEX=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_TRUSTED_HOST=mirrors.aliyun.com
RUN pip install --no-cache-dir -r requirements.txt -i ${PIP_INDEX} --trusted-host ${PIP_TRUSTED_HOST}

COPY . .

EXPOSE 5001
CMD ["gunicorn", "-w", "1", "--threads", "8", "-b", "0.0.0.0:5001", "--timeout", "120", "app:app"]
