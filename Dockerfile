# Imagen base ligera con Python 3.10
FROM python:3.10-slim

# Instalar dependencias del sistema necesarias para pdfplumber
RUN apt-get update && apt-get install -y \
    build-essential \
    libpoppler-cpp-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Crear carpeta de trabajo
WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el proyecto
COPY . .

# Exponer puerto
EXPOSE 8080

# Comando de inicio
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app", "--timeout", "300"]