from contextlib import asynccontextmanager, contextmanager
from datetime import date
from pathlib import Path
from typing import Literal
import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from database import get_connection, hay_solapamiento, initialize_database, verify_password

HORA = r"^([01]\d|2[0-3]):[0-5]\d$"
CORREO = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class Cliente(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    telefono: str = Field(min_length=1, max_length=30)
    email: str = Field(min_length=3, max_length=120, pattern=CORREO)


class Espacio(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    tipo: Literal["mesa", "zona de lectura", "sala privada"]
    capacidad: int = Field(gt=0)
    estado: Literal["disponible", "mantenimiento"] = "disponible"


class Reserva(BaseModel):
    id_cliente: int
    id_espacio: int
    fecha: date
    hora_inicio: str = Field(pattern=HORA)
    hora_fin: str = Field(pattern=HORA)
    num_personas: int = Field(gt=0)
    estado: Literal["pendiente", "confirmada", "cancelada"] = "pendiente"


class CategoriaMenu(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)


class ProductoMenu(BaseModel):
    id_categoria: int
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str = Field(min_length=1, max_length=200)
    precio: float = Field(ge=0)
    stock: int = Field(ge=0)
    disponible: bool = True


class Genero(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)


class Libro(BaseModel):
    id_genero: int
    titulo: str = Field(min_length=1, max_length=150)
    autor: str = Field(min_length=1, max_length=100)
    ejemplares: int = Field(ge=0)
    disponible: bool = True


class ReservaPublica(Cliente):
    id_espacio: int
    fecha: date
    hora_inicio: str = Field(pattern=HORA)
    hora_fin: str = Field(pattern=HORA)
    num_personas: int = Field(gt=0)


class Login(BaseModel):
    email: str
    password: str


MODELS = {
    "clientes": Cliente,
    "espacios": Espacio,
    "reservas": Reserva,
    "categorias_menu": CategoriaMenu,
    "productos_menu": ProductoMenu,
    "generos": Genero,
    "libros": Libro,
}
PRIMARY_KEYS = {
    "clientes": "id_cliente",
    "espacios": "id_espacio",
    "reservas": "id_reserva",
    "categorias_menu": "id_categoria",
    "productos_menu": "id_producto",
    "generos": "id_genero",
    "libros": "id_libro",
}
TABLES = set(MODELS)
PUBLIC_READ = {"libros", "generos", "productos_menu", "categorias_menu", "espacios"}

LIST_SQL = {
    "reservas": (
        "SELECT r.*, c.nombre AS cliente, e.nombre AS espacio FROM reservas r "
        "JOIN clientes c ON c.id_cliente = r.id_cliente "
        "JOIN espacios e ON e.id_espacio = r.id_espacio "
        "ORDER BY r.fecha DESC, r.hora_inicio"
    ),
    "productos_menu": (
        "SELECT p.*, c.nombre AS categoria FROM productos_menu p "
        "JOIN categorias_menu c ON c.id_categoria = p.id_categoria ORDER BY p.id_producto"
    ),
    "libros": (
        "SELECT l.*, g.nombre AS genero FROM libros l "
        "JOIN generos g ON g.id_genero = l.id_genero ORDER BY l.id_libro"
    ),
}

SECRET = os.environ.get("SECRET_KEY", "cambie-esta-clave-antes-de-publicar").encode()
SESION_SEGUNDOS = 8 * 3600


@contextmanager
def db(escritura: bool = False):
    conn = get_connection()
    try:
        with conn:
            if escritura:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
    finally:
        conn.close()


def db_error(exc: sqlite3.IntegrityError):
    texto = str(exc)
    if "UNIQUE" in texto:
        raise HTTPException(409, "Ya existe un registro con ese valor.") from exc
    raise HTTPException(
        409, "No se puede completar la operación: el registro está relacionado con otros datos."
    ) from exc


def quoted_columns(data: dict):
    return list(data), list(data.values())


def serialize(row):
    return dict(row)


def check_table(table: str):
    if table not in TABLES:
        raise HTTPException(404, "Entidad no encontrada")


def parse(table: str, payload: dict) -> dict:
    try:
        modelo = MODELS[table].model_validate(payload)
    except ValidationError as exc:
        mensaje = "; ".join(
            f"{'.'.join(str(parte) for parte in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise HTTPException(422, mensaje) from exc
    data = modelo.model_dump(mode="json")
    return {k: int(v) if isinstance(v, bool) else v for k, v in data.items()}


def validar_reserva(conn, data: dict, excluir_id: int | None = None):
    espacio = conn.execute(
        "SELECT * FROM espacios WHERE id_espacio = ?", (data["id_espacio"],)
    ).fetchone()
    if not espacio:
        raise HTTPException(404, "El espacio indicado no existe.")
    if not conn.execute(
        "SELECT 1 FROM clientes WHERE id_cliente = ?", (data["id_cliente"],)
    ).fetchone():
        raise HTTPException(404, "El cliente indicado no existe.")
    if data["hora_fin"] <= data["hora_inicio"]:
        raise HTTPException(400, "La hora de fin debe ser posterior a la de inicio.")
    if data["estado"] == "cancelada":
        return
    if espacio["estado"] != "disponible":
        raise HTTPException(409, "Ese espacio está en mantenimiento.")
    if data["num_personas"] > espacio["capacidad"]:
        raise HTTPException(400, f"El espacio solo tiene capacidad para {espacio['capacidad']} personas.")
    if hay_solapamiento(
        conn, data["id_espacio"], data["fecha"], data["hora_inicio"], data["hora_fin"], excluir_id
    ):
        raise HTTPException(409, "Ese espacio ya está reservado en ese horario.")


def crear_token(email: str) -> str:
    cuerpo = base64.urlsafe_b64encode(
        json.dumps({"sub": email, "exp": int(time.time()) + SESION_SEGUNDOS}).encode()
    ).decode()
    firma = hmac.new(SECRET, cuerpo.encode(), hashlib.sha256).hexdigest()
    return f"{cuerpo}.{firma}"


def requiere_admin(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Debe iniciar sesión.")
    try:
        cuerpo, firma = authorization[7:].split(".")
        esperada = hmac.new(SECRET, cuerpo.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(firma, esperada):
            raise ValueError("firma inválida")
        datos = json.loads(base64.urlsafe_b64decode(cuerpo.encode()))
        if datos["exp"] < time.time():
            raise ValueError("sesión vencida")
    except Exception as exc:
        raise HTTPException(401, "Sesión inválida o vencida.") from exc
    return datos["sub"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Berry & Books", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/api/login")
def login(datos: Login):
    with db() as conn:
        usuario = conn.execute("SELECT * FROM usuarios WHERE email = ?", (datos.email,)).fetchone()
    if not usuario or not verify_password(datos.password, usuario["password_hash"]):
        raise HTTPException(401, "Correo o contraseña incorrectos.")
    return {"token": crear_token(usuario["email"]), "nombre": usuario["nombre"]}


@app.post("/api/reservar", status_code=201)
def reservar(datos: ReservaPublica):
    if datos.fecha < date.today():
        raise HTTPException(400, "La fecha de la reserva no puede estar en el pasado.")
    with db(escritura=True) as conn:
        cliente = conn.execute(
            "SELECT id_cliente FROM clientes WHERE email = ?", (datos.email,)
        ).fetchone()
        if cliente:
            id_cliente = cliente["id_cliente"]
            conn.execute(
                "UPDATE clientes SET nombre = ?, telefono = ? WHERE id_cliente = ?",
                (datos.nombre, datos.telefono, id_cliente),
            )
        else:
            id_cliente = conn.execute(
                "INSERT INTO clientes (nombre, telefono, email) VALUES (?, ?, ?)",
                (datos.nombre, datos.telefono, datos.email),
            ).lastrowid
        reserva = {
            "id_cliente": id_cliente,
            "id_espacio": datos.id_espacio,
            "fecha": datos.fecha.isoformat(),
            "hora_inicio": datos.hora_inicio,
            "hora_fin": datos.hora_fin,
            "num_personas": datos.num_personas,
            "estado": "pendiente",
        }
        validar_reserva(conn, reserva)
        cur = conn.execute(
            "INSERT INTO reservas (id_cliente, id_espacio, fecha, hora_inicio, hora_fin, num_personas, estado) "
            "VALUES (:id_cliente, :id_espacio, :fecha, :hora_inicio, :hora_fin, :num_personas, :estado)",
            reserva,
        )
    return {"id_reserva": cur.lastrowid, "estado": "pendiente"}


@app.get("/api/{table}")
def list_rows(table: str, authorization: str | None = Header(default=None)):
    check_table(table)
    if table not in PUBLIC_READ:
        requiere_admin(authorization)
    with db() as conn:
        return [serialize(row) for row in conn.execute(LIST_SQL.get(table, f"SELECT * FROM {table}"))]


@app.get("/api/{table}/{key}")
def get_row(table: str, key: int, authorization: str | None = Header(default=None)):
    check_table(table)
    if table not in PUBLIC_READ:
        requiere_admin(authorization)
    with db() as conn:
        row = conn.execute(
            f"SELECT * FROM {table} WHERE {PRIMARY_KEYS[table]} = ?", (key,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Registro no encontrado")
    return serialize(row)


@app.post("/api/{table}", status_code=201)
def create_row(table: str, payload: dict, _: str = Depends(requiere_admin)):
    check_table(table)
    data = parse(table, payload)
    columns, values = quoted_columns(data)
    try:
        with db(escritura=(table == "reservas")) as conn:
            if table == "reservas":
                validar_reserva(conn, data)
            cur = conn.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                values,
            )
            row = conn.execute(
                f"SELECT * FROM {table} WHERE {PRIMARY_KEYS[table]} = ?", (cur.lastrowid,)
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        db_error(exc)
    return serialize(row)


@app.put("/api/{table}/{key}")
def update_row(table: str, key: int, payload: dict, _: str = Depends(requiere_admin)):
    check_table(table)
    data = parse(table, payload)
    pk = PRIMARY_KEYS[table]
    try:
        with db(escritura=(table == "reservas")) as conn:
            if table == "reservas":
                validar_reserva(conn, data, excluir_id=key)
            result = conn.execute(
                f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in data)} WHERE {pk} = ?",
                [*data.values(), key],
            )
            if result.rowcount == 0:
                raise HTTPException(404, "Registro no encontrado")
            row = conn.execute(f"SELECT * FROM {table} WHERE {pk} = ?", (key,)).fetchone()
    except sqlite3.IntegrityError as exc:
        db_error(exc)
    return serialize(row)


@app.delete("/api/{table}/{key}", status_code=204)
def delete_row(table: str, key: int, _: str = Depends(requiere_admin)):
    check_table(table)
    try:
        with db() as conn:
            result = conn.execute(f"DELETE FROM {table} WHERE {PRIMARY_KEYS[table]} = ?", (key,))
            if result.rowcount == 0:
                raise HTTPException(404, "Registro no encontrado")
    except sqlite3.IntegrityError as exc:
        db_error(exc)


@app.get("/api/espacios/{id_espacio}/disponibilidad")
def space_availability(id_espacio: int, fecha: date):
    with db() as conn:
        if not conn.execute("SELECT 1 FROM espacios WHERE id_espacio = ?", (id_espacio,)).fetchone():
            raise HTTPException(404, "Espacio no encontrado")
        ocupados = conn.execute(
            "SELECT hora_inicio, hora_fin FROM reservas "
            "WHERE id_espacio = ? AND fecha = ? AND estado != 'cancelada' ORDER BY hora_inicio",
            (id_espacio, fecha.isoformat()),
        ).fetchall()
    return {"id_espacio": id_espacio, "fecha": fecha.isoformat(), "ocupados": [serialize(o) for o in ocupados]}
