FROM python:3.10-slim

# 1. 安装系统依赖（包括编译工具）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 2. 从源码编译安装 TA-Lib
RUN apt-get update && \
    apt-get install -y build-essential && \
    wget https://downloads.sourceforge.net/project/ta-lib/ta-lib/0.4.0/ta-lib-0.4.0-src.tar.gz && \
    tar -xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib && \
    ./configure --prefix=/usr && \
    make && \
    make install
    # 创建必要的符号链接
RUN ln -s /usr/lib/libta_lib.so.0 /usr/lib/libta-lib.so && \
    ldconfig && \
    rm -rf /tmp/ta-lib && \
    apt-get remove -y build-essential wget && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y redis-tools && rm -rf /var/lib/apt/lists/*


# 4. 设置环境变量确保能找到库文件
ENV LD_LIBRARY_PATH=/usr/lib:$LD_LIBRARY_PATH

# 5. 安装Python依赖
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir numpy==1.23.0 && \
    pip install --no-cache-dir TA-Lib==0.4.21 && \
    pip install --no-cache-dir -r requirements.txt

    # 5. 清理不必要的编译工具（减小镜像大小）
RUN apt-get remove -y build-essential gcc g++ make wget && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*
# 6. 复制应用代码
COPY . .

# 7. 设置默认命令
CMD ["python", "your_script.py"]