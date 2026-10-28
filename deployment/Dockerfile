# Recipe for the container image that Azure or AWS will run.

# Start from a small official Python image.
FROM python:3.12-slim

# Print logs straight away and skip .pyc files.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Install packages first, so Docker can reuse this step when only the code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app and the rankings file.
COPY app ./app
COPY data ./data

# Run as a normal user instead of root (safer).
RUN useradd --create-home appuser
USER appuser

# The app listens on port 8000.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
