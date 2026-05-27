# Libreria Eliz

Aplicacion web simple para gestionar stock, ventas, ganancias e historial.

Esta hecha con Python y Flask. Los datos se guardan en SQLite.

## Requisitos

- Python 3 instalado

## Como ejecutar el proyecto

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

4. Instalar dependencias:

```bash
pip install -r requirements.txt
```

5. Ejecutar la aplicacion:

```bash
python app.py
```

6. Abrir el navegador en:

```text
http://127.0.0.1:5000
```

## Funcionalidades

- Agregar productos con nombre, detalle, precio, costo y stock.
- Importar productos desde Excel.
- Vender productos y descontar stock.
- Registrar historial de ventas.
- Calcular ventas, costos, ganancias e inversion en stock.
- Editar productos desde la tabla.
- Deshacer la ultima venta.
- Eliminar productos.
- Buscar y filtrar productos.

## Base de datos

La aplicacion usa SQLite y crea automaticamente el archivo `database.db` si no existe.

Si existe una base anterior llamada `libreria_eliz.db`, la app la migra automaticamente a `database.db` la primera vez que la base nueva esta vacia.

Tambien crea backups automaticos de la base antes de guardar cambios. Por defecto quedan en la carpeta `backups`.

## Render

Para que SQLite sea permanente en Render, configura un Persistent Disk y guarda la base dentro de ese disco.

Una configuracion simple:

```text
DATABASE_PATH=/var/data/database.db
BACKUP_DIR=/var/data/backups
```

Si Render tiene montado `/var/data`, la app intenta usar esa ruta automaticamente.
