from pathlib import Path
import hashlib
import hmac
import os
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "berry_books.db"
if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp") / "berry_books.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
  id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  telefono TEXT NOT NULL,
  email TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS espacios (
  id_espacio INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE,
  tipo TEXT NOT NULL CHECK(tipo IN ('mesa', 'zona de lectura', 'sala privada')),
  capacidad INTEGER NOT NULL CHECK(capacidad > 0),
  estado TEXT NOT NULL DEFAULT 'disponible' CHECK(estado IN ('disponible', 'mantenimiento'))
);
CREATE TABLE IF NOT EXISTS reservas (
  id_reserva INTEGER PRIMARY KEY AUTOINCREMENT,
  id_cliente INTEGER NOT NULL,
  id_espacio INTEGER NOT NULL,
  fecha TEXT NOT NULL,
  hora_inicio TEXT NOT NULL,
  hora_fin TEXT NOT NULL,
  num_personas INTEGER NOT NULL CHECK(num_personas > 0),
  estado TEXT NOT NULL DEFAULT 'pendiente' CHECK(estado IN ('pendiente', 'confirmada', 'cancelada')),
  CHECK(hora_fin > hora_inicio),
  FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE RESTRICT,
  FOREIGN KEY (id_espacio) REFERENCES espacios(id_espacio) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_reservas_espacio_fecha ON reservas(id_espacio, fecha);
CREATE TABLE IF NOT EXISTS categorias_menu (
  id_categoria INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS productos_menu (
  id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
  id_categoria INTEGER NOT NULL,
  nombre TEXT NOT NULL,
  descripcion TEXT NOT NULL,
  precio REAL NOT NULL CHECK(precio >= 0),
  stock INTEGER NOT NULL CHECK(stock >= 0),
  disponible INTEGER NOT NULL DEFAULT 1 CHECK(disponible IN (0, 1)),
  FOREIGN KEY (id_categoria) REFERENCES categorias_menu(id_categoria) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS generos (
  id_genero INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS libros (
  id_libro INTEGER PRIMARY KEY AUTOINCREMENT,
  id_genero INTEGER NOT NULL,
  titulo TEXT NOT NULL,
  autor TEXT NOT NULL,
  ejemplares INTEGER NOT NULL CHECK(ejemplares >= 0),
  disponible INTEGER NOT NULL DEFAULT 1 CHECK(disponible IN (0, 1)),
  FOREIGN KEY (id_genero) REFERENCES generos(id_genero) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS usuarios (
  id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  rol TEXT NOT NULL DEFAULT 'administrador'
);
"""


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    salt_hex, _ = stored.split("$")
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex)), stored)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hay_solapamiento(conn, id_espacio, fecha, hora_inicio, hora_fin, excluir_id=None):
    sql = (
        "SELECT 1 FROM reservas WHERE id_espacio = ? AND fecha = ? AND estado != 'cancelada' "
        "AND hora_inicio < ? AND hora_fin > ?"
    )
    params = [id_espacio, fecha, hora_fin, hora_inicio]
    if excluir_id is not None:
        sql += " AND id_reserva != ?"
        params.append(excluir_id)
    return conn.execute(sql + " LIMIT 1", params).fetchone() is not None


def seed_database(conn):
    if conn.execute("SELECT COUNT(*) FROM espacios").fetchone()[0] > 0:
        return

    conn.executemany("INSERT INTO generos (nombre) VALUES (?)", [
        ("Novela",), ("Fantasía",), ("Poesía",), ("Misterio",), ("Ciencia ficción",),
    ])
    conn.executemany(
        "INSERT INTO libros (id_genero, titulo, autor, ejemplares, disponible) VALUES (?, ?, ?, ?, ?)", [
            (1, "Cien años de soledad", "Gabriel García Márquez", 3, 1),
            (1, "Marcos Ramírez", "Carlos Luis Fallas", 2, 1),
            (2, "El hobbit", "J. R. R. Tolkien", 2, 1),
            (3, "Veinte poemas de amor", "Pablo Neruda", 1, 1),
            (4, "Los crímenes de la calle Morgue", "Edgar Allan Poe", 2, 1),
            (5, "Fahrenheit 451", "Ray Bradbury", 0, 0),
        ])

    conn.executemany("INSERT INTO categorias_menu (nombre) VALUES (?)", [
        ("Pasteles",), ("Galletas",), ("Bebidas calientes",), ("Bebidas frías",),
    ])
    conn.executemany(
        "INSERT INTO productos_menu (id_categoria, nombre, descripcion, precio, stock, disponible) VALUES (?, ?, ?, ?, ?, ?)", [
            (1, "Pastel de frutos rojos", "Bizcocho con crema y fresas, moras y arándanos", 3500, 8, 1),
            (1, "Tres leches", "Clásico pastel húmedo con crema batida", 3000, 10, 1),
            (2, "Galleta de avena", "Con pasas y un toque de canela", 1200, 20, 1),
            (3, "Café latte", "Espresso con leche vaporizada", 2200, 50, 1),
            (3, "Chocolate caliente", "Cacao costarricense con leche", 2400, 40, 1),
            (4, "Frappé de moca", "Café, chocolate y hielo frappé", 2800, 0, 0),
        ])

    conn.executemany("INSERT INTO espacios (nombre, tipo, capacidad, estado) VALUES (?, ?, ?, ?)", [
        ("Mesa Ventana", "mesa", 2, "disponible"),
        ("Mesa Jardín", "mesa", 4, "disponible"),
        ("Rincón Poesía", "zona de lectura", 6, "disponible"),
        ("Sala Biblioteca", "sala privada", 10, "disponible"),
        ("Mesa Esquina", "mesa", 2, "mantenimiento"),
    ])
    conn.executemany("INSERT INTO clientes (nombre, telefono, email) VALUES (?, ?, ?)", [
        ("Sofía Mora Vargas", "8888-1111", "sofia.mora@example.com"),
        ("Daniel Rojas Solís", "8777-2222", "daniel.rojas@example.com"),
        ("Valeria Jiménez Cruz", "8666-3333", "valeria.jimenez@example.com"),
    ])
    conn.executemany(
        "INSERT INTO reservas (id_cliente, id_espacio, fecha, hora_inicio, hora_fin, num_personas, estado) VALUES (?, ?, ?, ?, ?, ?, ?)", [
            (1, 1, "2026-10-12", "14:00", "16:00", 2, "confirmada"),
            (2, 3, "2026-10-12", "15:00", "18:00", 5, "confirmada"),
            (3, 4, "2026-10-13", "10:00", "12:00", 8, "pendiente"),
            (1, 2, "2026-10-14", "17:00", "19:00", 3, "cancelada"),
        ])

    conn.execute(
        "INSERT INTO usuarios (nombre, email, password_hash, rol) VALUES (?, ?, ?, ?)",
        ("Administrador", "admin@berryandbooks.com", hash_password("admin123"), "administrador"))


def initialize_database():
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        seed_database(conn)


if __name__ == "__main__":
    initialize_database()
    print(f"Base de datos lista en: {DB_PATH}")
