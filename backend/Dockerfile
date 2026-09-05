FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Nunca root. Si alguien logra ejecutar codigo dentro del contenedor, la
# diferencia entre root y `nobody` es la diferencia entre escaparse por un
# fallo del nucleo y no tener por donde empezar. La aplicacion solo lee: no
# escribe nada en el sistema de archivos.
USER 65534:65534
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
