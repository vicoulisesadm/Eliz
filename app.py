import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError


app = Flask(__name__)

database_uri = os.environ.get("DATABASE_URL")

if not database_uri:
    default_database_file = (
        Path("/var/data/database.db")
        if os.environ.get("RENDER") and Path("/var/data").exists()
        else Path("database.db")
    )
    database_uri = f"sqlite:///{default_database_file}"

if database_uri.startswith("postgres://"):
    database_uri = database_uri.replace("postgres://", "postgresql+psycopg://", 1)
elif database_uri.startswith("postgresql://"):
    database_uri = database_uri.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

LEGACY_DATABASE_FILE = Path("database.db")
OLDER_DATABASE_FILE = Path("libreria_eliz.db")
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "backups"))
database_initialized = False


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    author = db.Column(db.String(300), nullable=False)
    price = db.Column(db.Float, nullable=False, default=0)
    cost = db.Column(db.Float, nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0, index=True)


class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    product_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price_unit = db.Column(db.Float, nullable=False, default=0)
    cost_unit = db.Column(db.Float, nullable=False, default=0)
    total_sale = db.Column(db.Float, nullable=False, default=0)
    total_cost = db.Column(db.Float, nullable=False, default=0)
    profit = db.Column(db.Float, nullable=False, default=0)
    sale_date = db.Column(db.String(10), nullable=False, index=True)
    sale_time = db.Column(db.String(8), nullable=False)

    product = db.relationship("Product", backref="sales")


def is_sqlite_database():
    return app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite")


def backup_database():
    if not is_sqlite_database():
        return

    database_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "", 1)
    database_file = Path(database_path)

    if not database_file.exists():
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    shutil.copy2(database_file, BACKUP_DIR / f"database_{timestamp}.db")


def product_to_dict(product):
    return {
        "id": product.id,
        "title": product.title,
        "author": product.author,
        "price": float(product.price),
        "cost": float(product.cost),
        "stock": int(product.stock),
    }


def sale_to_dict(sale):
    return {
        "id": sale.id,
        "product_id": sale.product_id,
        "producto": sale.product_name,
        "cantidad": sale.quantity,
        "precioUnitario": float(sale.price_unit),
        "costoUnitario": float(sale.cost_unit),
        "totalVenta": float(sale.total_sale),
        "costoTotal": float(sale.total_cost),
        "ganancia": float(sale.profit),
        "fecha": sale.sale_date,
        "hora": sale.sale_time,
    }


def normalize_product(product):
    return {
        "id": product["id"],
        "title": product["title"],
        "author": product["author"],
        "price": float(product["price"]),
        "cost": float(product.get("cost", 0.0)),
        "stock": int(product["stock"]),
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
    price_unit = sale.get("precioUnitario", sale.get("priceUnitario", sale.get("price", 0.0)))
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


def migrate_from_sqlite_file(sqlite_file):
    if not sqlite_file.exists():
        return

    connection = sqlite3.connect(sqlite_file)
    connection.row_factory = sqlite3.Row

    try:
        tables = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }

        if not {"products", "sales"}.issubset(tables):
            return

        for row in connection.execute("SELECT id, title, author, price, cost, stock FROM products ORDER BY id"):
            if db.session.get(Product, row["id"]) is not None:
                continue

            db.session.add(
                Product(
                    id=row["id"],
                    title=row["title"],
                    author=row["author"],
                    price=row["price"],
                    cost=row["cost"],
                    stock=row["stock"],
                )
            )

        for row in connection.execute(
            """
            SELECT
                product_id, product_name, quantity, price_unit, cost_unit,
                total_sale, total_cost, profit, sale_date, sale_time
            FROM sales
            ORDER BY id
            """
        ):
            db.session.add(
                Sale(
                    product_id=row["product_id"],
                    product_name=row["product_name"],
                    quantity=row["quantity"],
                    price_unit=row["price_unit"],
                    cost_unit=row["cost_unit"],
                    total_sale=row["total_sale"],
                    total_cost=row["total_cost"],
                    profit=row["profit"],
                    sale_date=row["sale_date"],
                    sale_time=row["sale_time"],
                )
            )

        db.session.commit()
    finally:
        connection.close()


def initialize_database():
    global database_initialized

    db.create_all()

    has_products = db.session.query(Product.id).first() is not None
    has_sales = db.session.query(Sale.id).first() is not None

    if has_products or has_sales:
        database_initialized = True
        return

    migrate_from_sqlite_file(LEGACY_DATABASE_FILE)

    if db.session.query(Product.id).first() is None and OLDER_DATABASE_FILE != LEGACY_DATABASE_FILE:
        migrate_from_sqlite_file(OLDER_DATABASE_FILE)

    database_initialized = True


@app.before_request
def ensure_database_is_ready():
    if database_initialized:
        return

    initialize_database()


def load_books():
    products = Product.query.order_by(Product.id).all()
    return [product_to_dict(product) for product in products]


def load_sales():
    sales = Sale.query.order_by(Sale.id).all()
    return [sale_to_dict(sale) for sale in sales]


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
        db.session.add(
            Product(
                title=request.form["title"].strip(),
                author=request.form["author"].strip(),
                price=float(request.form["price"]),
                cost=float(request.form["cost"]),
                stock=int(request.form["stock"]),
            )
        )
        db.session.commit()
    except (KeyError, ValueError, SQLAlchemyError):
        db.session.rollback()

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

    try:
        for _, row in data_frame.iterrows():
            new_product = build_product_from_row(row)

            if new_product is None:
                continue

            db.session.add(Product(**new_product))

        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()

    return redirect(url_for("index"))


@app.route("/update-stock/<int:book_id>", methods=["POST"])
def update_stock(book_id):
    backup_database()

    try:
        product = db.session.get(Product, book_id)

        if product is not None:
            product.stock = int(request.form["stock"])
            db.session.commit()
    except (KeyError, ValueError, SQLAlchemyError):
        db.session.rollback()

    return redirect(url_for("index"))


@app.route("/update-product/<int:book_id>", methods=["POST"])
def update_product(book_id):
    backup_database()

    try:
        product = db.session.get(Product, book_id)

        if product is not None:
            product.title = request.form["title"].strip()
            product.author = request.form["author"].strip()
            product.price = float(request.form["price"])
            product.cost = float(request.form["cost"])
            product.stock = int(request.form["stock"])
            db.session.commit()
    except (KeyError, ValueError, SQLAlchemyError):
        db.session.rollback()

    return redirect(url_for("index"))


@app.route("/sell/<int:book_id>", methods=["POST"])
def sell_book(book_id):
    backup_database()
    now = datetime.now()

    try:
        product = db.session.get(Product, book_id)

        if product is None or product.stock <= 0:
            return redirect(url_for("index"))

        quantity = 1
        total_sale = float(product.price) * quantity
        total_cost = float(product.cost) * quantity
        profit = total_sale - total_cost
        product.stock -= quantity

        db.session.add(
            Sale(
                product_id=product.id,
                product_name=product.title,
                quantity=quantity,
                price_unit=product.price,
                cost_unit=product.cost,
                total_sale=total_sale,
                total_cost=total_cost,
                profit=profit,
                sale_date=now.strftime("%Y-%m-%d"),
                sale_time=now.strftime("%H:%M:%S"),
            )
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()

    return redirect(url_for("index"))


@app.route("/undo-last-sale", methods=["POST"])
def undo_last_sale():
    backup_database()

    try:
        last_sale = Sale.query.order_by(Sale.id.desc()).first()

        if last_sale is None:
            return redirect(url_for("index"))

        product = None

        if last_sale.product_id is not None:
            product = db.session.get(Product, last_sale.product_id)

        if product is None:
            product = Product.query.filter_by(title=last_sale.product_name).order_by(Product.id).first()

        if product is not None:
            product.stock += last_sale.quantity

        db.session.delete(last_sale)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()

    return redirect(url_for("index"))


@app.route("/reset-data", methods=["POST"])
def reset_data():
    try:
        Sale.query.delete()
        if request.form.get("delete_products") == "yes":
            Product.query.delete()
        db.session.commit()
    except Exception:
        db.session.rollback()
    return redirect(url_for("index"))


@app.route("/delete-product/<int:book_id>", methods=["POST"])
def delete_product(book_id):
    backup_database()

    try:
        product = db.session.get(Product, book_id)

        if product is not None:
            db.session.delete(product)
            db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()

    return redirect(url_for("index"))


with app.app_context():
    initialize_database()


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True, use_reloader=False)
