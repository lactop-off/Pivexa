FROM python:3.11-slim

# WeasyPrint / matplotlib に必要なシステムライブラリ
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi-dev libcairo2 fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# matplotlib のフォントキャッシュをビルド時に生成しておく。
# これを省くと、ワーカーでの初回チャート描画時にフォントスキャン（約40秒）が走り、
# 「最初の解析だけ極端に遅い／ハングして見える」原因になる。
RUN python -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; plt.plot([0, 1]); plt.savefig('/tmp/_warm.png')" \
    && rm -f /tmp/_warm.png

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
