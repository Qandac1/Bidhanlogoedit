FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# ffmpeg = render engine; tesseract = OCR for phone-number detection;
# libgl/glib = OpenCV runtime; fonts-dejavu = scroll-text font.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    fonts-dejavu-core \
    ca-certificates \
    rclone \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data = sessions + temp work dirs (mounted volume in compose)
RUN mkdir -p /app/data /app/work && chmod 755 /app/data /app/work

CMD ["python", "-u", "bot.py"]
