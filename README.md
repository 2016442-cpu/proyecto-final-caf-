# Berry & Books

**Catálogo y Reserva de un Cozy Book Café**: plataforma web para la gestión de reservas e inventario
de un café temático de lectura.

## Descripción

Los clientes pueden explorar el catálogo de libros disponibles para leer en el local, ver el menú de
repostería y reservar mesas o zonas de lectura en un horario específico. El personal cuenta con un
panel de administración privado (con inicio de sesión) para gestionar libros, menú, espacios, clientes
y reservas.

La regla principal del sistema: **un espacio no puede reservarse dos veces en un mismo rango de fecha y
hora**. El backend lo valida antes de guardar cualquier reserva (las reservas canceladas no ocupan el espacio).

El análisis del problema, el diagrama entidad-relación y la descripción de las tablas están en
[`docs/analisis_y_diseno.md`](docs/analisis_y_diseno.md).

## Tecnologías utilizadas

- **Python** y **FastAPI** (backend y API REST)
- **SQLite** (base de datos)
- **HTML, CSS y JavaScript** (frontend)
- **GitHub** (control de versiones) y **Vercel** (publicación)

## Instalación

1. Instale Python 3.10 o superior.
2. En la carpeta del proyecto, cree y active un entorno virtual:

   ```bash
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # macOS / Linux
   ```

3. Instale las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

## Ejecución

```bash
uvicorn main:app --reload
```

Abra <http://127.0.0.1:8000> en el navegador. La base de datos (`berry_books.db`) se crea sola con datos
de ejemplo la primera vez que se ejecuta. La documentación automática de la API está en
<http://127.0.0.1:8000/docs>.

**Cuenta de administrador de ejemplo:** `admin@berryandbooks.com` / `admin123`
(cámbiela antes de publicar el proyecto).

## Estructura del sistema

```
berry-and-books/
├── main.py            # API FastAPI: modelos, validaciones, login y endpoints CRUD
├── database.py        # Esquema SQLite, datos de ejemplo y regla de solapamiento
├── berry_books.db     # Base de datos SQLite
├── requirements.txt   # Dependencias
├── static/
│   ├── index.html     # Página principal
│   ├── styles.css     # Estilos
│   └── app.js         # Interfaz: consume la API con fetch
└── docs/              # Análisis, diagrama entidad-relación y descripción de tablas
```

### Base de datos

Ocho tablas: `clientes`, `espacios`, `reservas`, `categorias_menu`, `productos_menu`, `generos`,
`libros` y `usuarios`. Llaves foráneas: `reservas.id_cliente`, `reservas.id_espacio`,
`productos_menu.id_categoria` y `libros.id_genero`.

### Endpoints

`{tabla}` puede ser: `reservas`, `espacios`, `clientes`, `libros`, `generos`, `productos_menu`
o `categorias_menu`.

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| GET | `/api/{tabla}` | Público en `libros`, `generos`, `productos_menu`, `categorias_menu` y `espacios`; con sesión en `clientes` y `reservas` | Listar registros |
| GET | `/api/{tabla}/{id}` | Igual que el anterior | Consultar un registro |
| POST | `/api/{tabla}` | Administrador | Crear un registro |
| PUT | `/api/{tabla}/{id}` | Administrador | Modificar un registro |
| DELETE | `/api/{tabla}/{id}` | Administrador | Eliminar un registro |
| GET | `/api/espacios/{id}/disponibilidad?fecha=AAAA-MM-DD` | Público | Horarios ya ocupados de un espacio |
| POST | `/api/reservar` | Público | Reserva de un cliente (valida solapamientos) |
| POST | `/api/login` | Público | Iniciar sesión como administrador |

## Publicación en Vercel

1. Suba el proyecto a un repositorio de GitHub.
2. En Vercel, importe el repositorio (el framework FastAPI se detecta automáticamente).
3. (Opcional) Defina la variable de entorno `SECRET_KEY` con un texto largo y aleatorio.

> **Nota:** Vercel solo permite escribir en una carpeta temporal, por lo que en la versión publicada la
> base de datos se reinicia con los datos de ejemplo cada cierto tiempo. En el equipo local los datos
> se guardan de forma permanente en `berry_books.db`.
