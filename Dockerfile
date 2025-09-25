FROM python:3.10-slim

# 1. 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 2. 直接安装TA-Lib（让pip自动选择兼容版本）
RUN pip install --upgrade pip && \
    pip install --no-cache-dir numpy==1.23.0 && \
    pip install --no-cache-dir TA-Lib  # 不指定版本，让pip选择兼容版本

# 3. 安装其他运行时依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "your_script.py"]