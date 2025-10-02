FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code (copie initiale — sera surmontée par le bind-mount en dev)
COPY . .

# Port Flask
EXPOSE 5000



# Lancement "mode dev" (app.py contient déjà debug=True)
CMD ["python", "app.py"]