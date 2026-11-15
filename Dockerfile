# One image used by both the pipeline and the app.
FROM python:3.13-slim

WORKDIR /project

# install packages first so this layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
