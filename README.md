# Stock de librería

Aplicación web simple para gestionar el stock de una librería.

Está hecha con Python y Flask. Los datos se guardan en el archivo `books.json`.

## Requisitos

- Python 3 instalado

## Cómo ejecutar el proyecto

1. Abrir una terminal en la carpeta del proyecto.

2. Crear un entorno virtual:

```bash
python -m venv venv
```

3. Activar el entorno virtual.

En Windows:

```bash
venv\Scripts\activate
```

En macOS o Linux:

```bash
source venv/bin/activate
```

4. Instalar Flask:

```bash
pip install -r requirements.txt
```

5. Ejecutar la aplicación:

```bash
python app.py
```

6. Abrir el navegador en:

```text
http://127.0.0.1:5000
```

## Funcionalidades

- Agregar libros con título, autor, precio y cantidad en stock.
- Ver la lista de libros cargados.
- Actualizar el stock de cada libro.
- Guardar los datos en `books.json`.
