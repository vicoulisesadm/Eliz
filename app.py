import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, redirect, render_template, request, url_for


app = Flask(__name__)

DEFAULT_DATABASE_FILE = (
    Path("/var/data/database.db")
    if os.environ.get("RENDER") and Path("/var/data").exists()
    else Path("database.db")
)
DATABASE_FILE = Path(os.environ.get("DATABASE_PATH", DEFAULT_DATABASE_FILE))
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", DATABASE_FILE.parent / "backups"))
LEGACY_DATABASE_FILE = Path("libreria_eliz.db")


def get_connection():
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def backup_database():
    if not DATABASE_FILE.exists():
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_file = BACKUP_DIR / f"database_{timestamp}.db"
    shutil.copy2(DATABASE_FILE, backup_file)


def normalize_product(product):
    return {
        "id": product["id"],
        "title": product["title"],
        "author": product["author"],
        "price": float(product["price"]),
        "cost": float(product.get("cost", 0.0)),
        "stock": int(product["stock"]),
    }


def initialize_database():
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                price REAL NOT NULL DEFAULT 0,
                cost REAL NOT NULL DEFAULT 0,
                stock INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                price_unit REAL NOT NULL DEFAULT 0,
                cost_unit REAL NOT NULL DEFAULT 0,
                total_sale REAL NOT NULL DEFAULT 0,
                total_cost REAL NOT NULL DEFAULT 0,
                profit REAL NOT NULL DEFAULT 0,
                sale_date TEXT NOT NULL,
                sale_time TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_products_title ON products(title)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_products_stock ON products(stock)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_sales_product ON sales(product_id)")

        product_count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        sale_count = connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0]

    if product_count == 0 and sale_count == 0:
        migrate_from_legacy_sqlite()


def migrate_from_legacy_sqlite():
    if not LEGACY_DATABASE_FILE.exists() or LEGACY_DATABASE_FILE.resolve() == DATABASE_FILE.resolve():
        return

    legacy_connection = sqlite3.connect(LEGACY_DATABASE_FILE)
    legacy_connection.row_factory = sqlite3.Row

    try:
        legacy_tables = {
            row["name"]
            for row in legacy_connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

        if not {"products", "sales"}.issubset(legacy_tables):
            return

        with get_connection() as connection:
            for product in legacy_connection.execute(
                "SELECT id, title, author, price, cost, stock FROM products ORDER BY id"
            ).fetchall():
                connection.execute(
                    """
                    INSERT OR IGNORE INTO products (id, title, author, price, cost, stock)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        product["id"],
                        product["title"],
                        product["author"],
                        product["price"],
                        product["cost"],
                        product["stock"],
                    ),
                )

            for sale in legacy_connection.execute(
                """
                SELECT
                    product_id, product_name, quantity, price_unit, cost_unit,
                    total_sale, total_cost, profit, sale_date, sale_time
                FROM sales
                ORDER BY id
                """
            ).fetchall():
                connection.execute(
                    """
                    INSERT INTO sales (
                        product_id, product_name, quantity, price_unit, cost_unit,
                        total_sale, total_cost, profit, sale_date, sale_time
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sale["product_id"],
                        sale["product_name"],
                        sale["quantity"],
                        sale["price_unit"],
                        sale["cost_unit"],
                        sale["total_sale"],
                        sale["total_cost"],
                        sale["profit"],
                        sale["sale_date"],
                        sale["sale_time"],
                    ),
                )
    finally:
        legacy_connection.close()


def load_books():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, title, author, price, cost, stock FROM products ORDER BY id"
        ).fetchall()

    return [normalize_product(dict(row)) for row in rows]


def save_books(books):
    backup_database()

    with get_connection() as connection:
        connection.execute("DELETE FROM products")

        for product in books:
            normalized_product = normalize_product(product)
            connection.execute(
                """
                INSERT INTO products (id, title, author, price, cost, stock)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_product["id"],
                    normalized_product["title"],
                    normalized_product["author"],
                    normalized_product["price"],
                    normalized_product["cost"],
                    normalized_product["stock"],
                ),
            )


def load_sales():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id, product_id, product_name, quantity, price_unit, cost_unit,
                total_sale, total_cost, profit, sale_date, sale_time
            FROM sales
            ORDER BY id
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "product_id": row["product_id"],
            "producto": row["product_name"],
            "cantidad": row["quantity"],
            "precioUnitario": row["price_unit"],
            "costoUnitario": row["cost_unit"],
            "totalVenta": row["total_sale"],
            "costoTotal": row["total_cost"],
            "ganancia": row["profit"],
            "fecha": row["sale_date"],
            "hora": row["sale_time"],
        }
        for row in rows
    ]


def save_sales(sales):
    backup_database()

    with get_connection() as connection:
        connection.execute("DELETE FROM sales")

        for sale in sales:
            normalized_sale = normalize_sale(sale)
            connection.execute(
                """
                INSERT INTO sales (
                    product_id, product_name, quantity, price_unit, cost_unit,
                    total_sale, total_cost, profit, sale_date, sale_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_sale["product_id"],
                    normalized_sale["producto"],
                    normalized_sale["cantidad"],
                    normalized_sale["precioUnitario"],
                    normalized_sale["costoUnitario"],
                    normalized_sale["totalVenta"],
                    normalized_sale["costoTotal"],
                    normalized_sale["ganancia"],
                    normalized_sale["fecha"],
                    normalized_sale["hora"],
                ),
            )


def get_next_id(books):
    if not books:
        return 1

    return max(book["id"] for book in books) + 1


def build_product_from_row(row):
    product_name = str(row.get("producto", "")).strip()
    detail = str(row.get("detalle", "")).strip()

    if not product_name or not detail:
        return None

    price = pd.to_numeric(row.get("precio"), errors="coerce")
    cost = pd.to_numeric(row.get("costo"), errors="coerce")
    stock = pd.to_numeric(row.get("stock"), errors="coerce")

    if pd.isna(price) or pd.isna(cost) or pd.isna(stock):
        return None

    return {
        "title": product_name,
        "author": detail,
        "price": float(price),
        "cost": float(cost),
        "stock": int(stock),
    }


def get_sale_date(sale):
    if "date" in sale:
        return sale["date"]

    if "fecha" in sale:
        return sale["fecha"]

    if "date_time" in sale:
        return sale["date_time"].split(" ")[0]

    return datetime.now().strftime("%Y-%m-%d")


def get_sale_time(sale):
    if "hora" in sale:
        return sale["hora"]

    if "date_time" in sale and " " in sale["date_time"]:
        return sale["date_time"].split(" ")[1]

    return "00:00:00"


def normalize_sale(sale):
    quantity = sale.get("cantidad", sale.get("quantity", 1))
    price_unit = sale.get("priceUnitario", sale.get("price", 0.0))
    cost_unit = sale.get("costoUnitario", 0.0)
    total_sale = sale.get("totalVenta", price_unit * quantity)
    total_cost = sale.get("costoTotal", cost_unit * quantity)
    profit = sale.get("ganancia", total_sale - total_cost)

    return {
        "product_id": sale.get("product_id"),
        "producto": sale.get("producto", sale.get("product", "")),
        "cantidad": quantity,
        "precioUnitario": price_unit,
        "costoUnitario": cost_unit,
        "totalVenta": total_sale,
        "costoTotal": total_cost,
        "ganancia": profit,
        "fecha": get_sale_date(sale),
        "hora": get_sale_time(sale),
    }


def build_daily_stats(sales):
    stats_by_day = {}

    for sale in sales:
        normalized_sale = normalize_sale(sale)
        sale_date = normalized_sale["fecha"]

        if sale_date not in stats_by_day:
            stats_by_day[sale_date] = {
                "fecha": sale_date,
                "total_vendido": 0.0,
                "costo_total": 0.0,
                "ganancia_total": 0.0,
            }

        stats_by_day[sale_date]["total_vendido"] += normalized_sale["totalVenta"]
        stats_by_day[sale_date]["costo_total"] += normalized_sale["costoTotal"]
        stats_by_day[sale_date]["ganancia_total"] += normalized_sale["ganancia"]

    return stats_by_day


def build_product_sales_stats(sales):
    product_totals = {}

    for sale in sales:
        normalized_sale = normalize_sale(sale)
        product_name = normalized_sale["producto"]

        if not product_name:
            continue

        product_totals[product_name] = product_totals.get(product_name, 0) + normalized_sale["cantidad"]

    if not product_totals:
        return None

    product_name = max(product_totals, key=product_totals.get)

    return {
        "producto": product_name,
        "cantidad": product_totals[product_name],
    }


def group_sales_by_date(sales):
    grouped_sales = {}

    for sale in sales:
        normalized_sale = normalize_sale(sale)
        sale_date = normalized_sale["fecha"]

        if sale_date not in grouped_sales:
            grouped_sales[sale_date] = []

        grouped_sales[sale_date].append(normalized_sale)

    return dict(sorted(grouped_sales.items(), reverse=True))


def get_period_label(sale_date, period):
    date_value = datetime.strptime(sale_date, "%Y-%m-%d")

    if period == "week":
        year, week, _ = date_value.isocalendar()
        return f"{year}-S{week:02d}"

    if period == "month":
        return date_value.strftime("%Y-%m")

    return sale_date


def aggregate_sales_for_period(sales, period):
    grouped = {}

    for sale in sales:
        normalized_sale = normalize_sale(sale)
        label = get_period_label(normalized_sale["fecha"], period)

        if label not in grouped:
            grouped[label] = {
                "total_vendido": 0.0,
                "ganancia_total": 0.0,
                "costo_total": 0.0,
            }

        grouped[label]["total_vendido"] += normalized_sale["totalVenta"]
        grouped[label]["ganancia_total"] += normalized_sale["ganancia"]
        grouped[label]["costo_total"] += normalized_sale["costoTotal"]

    labels = sorted(grouped.keys())

    return {
        "labels": labels,
        "ventas": [grouped[label]["total_vendido"] for label in labels],
        "ganancias": [grouped[label]["ganancia_total"] for label in labels],
        "costos": [grouped[label]["costo_total"] for label in labels],
    }


def build_chart_data(products, sales):
    product_totals = {}

    for sale in sales:
        normalized_sale = normalize_sale(sale)
        product_name = normalized_sale["producto"]

        if not product_name:
            continue

        product_totals[product_name] = product_totals.get(product_name, 0) + normalized_sale["cantidad"]

    top_products = sorted(product_totals.items(), key=lambda item: item[1], reverse=True)[:10]
    stock_products = sorted(products, key=lambda product: product["stock"])[:15]

    return {
        "sales": {
            "day": aggregate_sales_for_period(sales, "day"),
            "week": aggregate_sales_for_period(sales, "week"),
            "month": aggregate_sales_for_period(sales, "month"),
        },
        "top_products": {
            "labels": [product_name for product_name, _ in top_products],
            "quantities": [quantity for _, quantity in top_products],
        },
        "stock": {
            "labels": [product["title"] for product in stock_products],
            "values": [product["stock"] for product in stock_products],
            "colors": [
                "rgba(220, 38, 38, 0.82)" if product["stock"] <= 2 else "rgba(37, 99, 235, 0.72)"
                for product in stock_products
            ],
        },
    }


def build_visual_summary(today_stats, sales, today):
    products_sold_today = 0

    for sale in sales:
        normalized_sale = normalize_sale(sale)

        if normalized_sale["fecha"] == today:
            products_sold_today += normalized_sale["cantidad"]

    return {
        "total_vendido_hoy": today_stats["total_vendido"],
        "ganancia_hoy": today_stats["ganancia_total"],
        "costo_hoy": today_stats["costo_total"],
        "productos_vendidos_hoy": products_sold_today,
    }


def find_product_for_sale(products, sale):
    normalized_sale = normalize_sale(sale)
    product_id = normalized_sale["product_id"]

    if product_id is not None:
        for product in products:
            if product["id"] == product_id:
                return product

    for product in products:
        if product["title"] == normalized_sale["producto"]:
            return product

    return None


@app.route("/")
def index():
    products = load_books()
    sales = load_sales()
    normalized_sales = [normalize_sale(sale) for sale in sales]
    normalized_sales.sort(key=lambda sale: (sale["fecha"], sale["hora"]), reverse=True)
    stats_by_day = build_daily_stats(sales)
    sales_by_date = group_sales_by_date(sales)
    best_selling_product = build_product_sales_stats(sales)
    today = datetime.now().strftime("%Y-%m-%d")
    total_invested = sum(product.get("cost", 0.0) * product["stock"] for product in products)
    today_stats = stats_by_day.get(
        today,
        {
            "fecha": today,
            "total_vendido": 0.0,
            "costo_total": 0.0,
            "ganancia_total": 0.0,
        },
    )

    best_day = None
    worst_day = None

    if stats_by_day:
        daily_stats = list(stats_by_day.values())
        best_day = max(daily_stats, key=lambda item: item["total_vendido"])
        worst_day = min(daily_stats, key=lambda item: item["total_vendido"])

    chart_data = build_chart_data(products, sales)
    visual_summary = build_visual_summary(today_stats, sales, today)

    return render_template(
        "index.html",
        products=products,
        sales=normalized_sales,
        sales_by_date=sales_by_date,
        today_stats=today_stats,
        best_day=best_day,
        worst_day=worst_day,
        best_selling_product=best_selling_product,
        total_invested=total_invested,
        chart_data=chart_data,
        visual_summary=visual_summary,
    )


@app.route("/add", methods=["POST"])
def add_book():
    backup_database()

    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO products (title, author, price, cost, stock)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request.form["title"].strip(),
                    request.form["author"].strip(),
                    float(request.form["price"]),
                    float(request.form["cost"]),
                    int(request.form["stock"]),
                ),
            )
    except (KeyError, ValueError, sqlite3.Error):
        return redirect(url_for("index"))

    return redirect(url_for("index"))


@app.route("/upload_excel", methods=["POST"])
def upload_excel():
    excel_file = request.files.get("excel_file")

    if excel_file is None or excel_file.filename == "":
        return redirect(url_for("index"))

    if not excel_file.filename.lower().endswith(".xlsx"):
        return redirect(url_for("index"))

    data_frame = pd.read_excel(excel_file)
    data_frame.columns = [str(column).strip().lower() for column in data_frame.columns]
    required_columns = {"producto", "detalle", "precio", "costo", "stock"}

    if not required_columns.issubset(data_frame.columns):
        return redirect(url_for("index"))

    backup_database()

    with get_connection() as connection:
        for _, row in data_frame.iterrows():
            new_product = build_product_from_row(row)

            if new_product is None:
                continue

            connection.execute(
                """
                INSERT INTO products (title, author, price, cost, stock)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    new_product["title"],
                    new_product["author"],
                    new_product["price"],
                    new_product["cost"],
                    new_product["stock"],
                ),
            )

    return redirect(url_for("index"))


@app.route("/update-stock/<int:book_id>", methods=["POST"])
def update_stock(book_id):
    backup_database()

    try:
        with get_connection() as connection:
            connection.execute(
                "UPDATE products SET stock = ? WHERE id = ?",
                (int(request.form["stock"]), book_id),
            )
    except (KeyError, ValueError, sqlite3.Error):
        return redirect(url_for("index"))

    return redirect(url_for("index"))


@app.route("/update-product/<int:book_id>", methods=["POST"])
def update_product(book_id):
    backup_database()

    try:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE products
                SET title = ?, author = ?, price = ?, cost = ?, stock = ?
                WHERE id = ?
                """,
                (
                    request.form["title"].strip(),
                    request.form["author"].strip(),
                    float(request.form["price"]),
                    float(request.form["cost"]),
                    int(request.form["stock"]),
                    book_id,
                ),
            )
    except (KeyError, ValueError, sqlite3.Error):
        return redirect(url_for("index"))

    return redirect(url_for("index"))


@app.route("/sell/<int:book_id>", methods=["POST"])
def sell_book(book_id):
    backup_database()
    now = datetime.now()

    try:
        with get_connection() as connection:
            product = connection.execute(
                "SELECT id, title, price, cost, stock FROM products WHERE id = ?",
                (book_id,),
            ).fetchone()

            if product is None or product["stock"] <= 0:
                return redirect(url_for("index"))

            quantity = 1
            total_sale = float(product["price"]) * quantity
            total_cost = float(product["cost"]) * quantity
            profit = total_sale - total_cost

            connection.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ?",
                (quantity, book_id),
            )
            connection.execute(
                """
                INSERT INTO sales (
                    product_id, product_name, quantity, price_unit, cost_unit,
                    total_sale, total_cost, profit, sale_date, sale_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product["id"],
                    product["title"],
                    quantity,
                    product["price"],
                    product["cost"],
                    total_sale,
                    total_cost,
                    profit,
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%H:%M:%S"),
                ),
            )
    except sqlite3.Error:
        return redirect(url_for("index"))

    return redirect(url_for("index"))


@app.route("/undo-last-sale", methods=["POST"])
def undo_last_sale():
    backup_database()

    try:
        with get_connection() as connection:
            last_sale = connection.execute(
                """
                SELECT id, product_id, product_name, quantity
                FROM sales
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

            if last_sale is None:
                return redirect(url_for("index"))

            if last_sale["product_id"] is not None:
                connection.execute(
                    "UPDATE products SET stock = stock + ? WHERE id = ?",
                    (last_sale["quantity"], last_sale["product_id"]),
                )
            else:
                connection.execute(
                    """
                    UPDATE products
                    SET stock = stock + ?
                    WHERE id = (
                        SELECT id FROM products WHERE title = ? ORDER BY id LIMIT 1
                    )
                    """,
                    (last_sale["quantity"], last_sale["product_name"]),
                )

            connection.execute("DELETE FROM sales WHERE id = ?", (last_sale["id"],))
    except sqlite3.Error:
        return redirect(url_for("index"))

    return redirect(url_for("index"))


@app.route("/reset-data", methods=["POST"])
def reset_data():
    backup_database()

    try:
        with get_connection() as connection:
            connection.execute("DELETE FROM sales")

            if request.form.get("delete_products") == "yes":
                connection.execute("DELETE FROM products")
    except sqlite3.Error:
        return redirect(url_for("index"))

    return redirect(url_for("index"))


@app.route("/delete-product/<int:book_id>", methods=["POST"])
def delete_product(book_id):
    backup_database()

    try:
        with get_connection() as connection:
            connection.execute("DELETE FROM products WHERE id = ?", (book_id,))
    except sqlite3.Error:
        return redirect(url_for("index"))

    return redirect(url_for("index"))


initialize_database()


if __name__ == "__main__":
    app.run(debug=True)
