import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, redirect, render_template, request, url_for


app = Flask(__name__)

DATA_FILE = Path("books.json")
SALES_FILE = Path("sales.json")


def load_books():
    if not DATA_FILE.exists():
        return []

    with DATA_FILE.open("r", encoding="utf-8") as file:
        books = json.load(file)

    # Asegura compatibilidad con productos guardados antes de agregar el costo.
    for book in books:
        book.setdefault("cost", 0.0)

    return books


def save_books(books):
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(books, file, indent=2, ensure_ascii=False)


def load_sales():
    if not SALES_FILE.exists():
        return []

    with SALES_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_sales(sales):
    with SALES_FILE.open("w", encoding="utf-8") as file:
        json.dump(sales, file, indent=2, ensure_ascii=False)


def get_next_id(books):
    if not books:
        return 1

    return max(book["id"] for book in books) + 1


def build_product_from_row(row, product_id):
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
        "id": product_id,
        "title": product_name,
        "author": detail,
        "price": float(price),
        "cost": float(cost),
        "stock": int(stock),
    }


def get_sale_date(sale):
    if "date" in sale:
        return sale["date"]

    if "date_time" in sale:
        return sale["date_time"].split(" ")[0]

    return datetime.now().strftime("%Y-%m-%d")


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
    stats_by_day = build_daily_stats(sales)
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

    return render_template(
        "index.html",
        products=products,
        today_stats=today_stats,
        best_day=best_day,
        worst_day=worst_day,
        total_invested=total_invested,
    )


@app.route("/add", methods=["POST"])
def add_book():
    products = load_books()

    new_product = {
        "id": get_next_id(products),
        "title": request.form["title"],
        "author": request.form["author"],
        "price": float(request.form["price"]),
        "cost": float(request.form["cost"]),
        "stock": int(request.form["stock"]),
    }

    products.append(new_product)
    save_books(products)

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

    products = load_books()
    next_id = get_next_id(products)

    for _, row in data_frame.iterrows():
        new_product = build_product_from_row(row, next_id)

        if new_product is None:
            continue

        products.append(new_product)
        next_id += 1

    save_books(products)

    return redirect(url_for("index"))


@app.route("/update-stock/<int:book_id>", methods=["POST"])
def update_stock(book_id):
    products = load_books()
    new_stock = int(request.form["stock"])

    for product in products:
        if product["id"] == book_id:
            product["stock"] = new_stock
            break

    save_books(products)

    return redirect(url_for("index"))


@app.route("/update-product/<int:book_id>", methods=["POST"])
def update_product(book_id):
    products = load_books()
    new_title = request.form["title"].strip()
    new_author = request.form["author"].strip()
    new_price = float(request.form["price"])
    new_cost = float(request.form["cost"])
    new_stock = int(request.form["stock"])

    for product in products:
        if product["id"] == book_id:
            product["title"] = new_title
            product["author"] = new_author
            product["price"] = new_price
            product["cost"] = new_cost
            product["stock"] = new_stock
            break

    save_books(products)

    return redirect(url_for("index"))


@app.route("/sell/<int:book_id>", methods=["POST"])
def sell_book(book_id):
    products = load_books()
    sales = load_sales()

    for product in products:
        if product["id"] == book_id and product["stock"] > 0:
            quantity = 1
            total_sale = product["price"] * quantity
            total_cost = product.get("cost", 0.0) * quantity
            profit = total_sale - total_cost

            product["stock"] -= quantity
            sales.append(
                {
                    "product_id": product["id"],
                    "producto": product["title"],
                    "cantidad": quantity,
                    "precioUnitario": product["price"],
                    "costoUnitario": product.get("cost", 0.0),
                    "totalVenta": total_sale,
                    "costoTotal": total_cost,
                    "ganancia": profit,
                    "fecha": datetime.now().strftime("%Y-%m-%d"),
                }
            )
            break

    save_books(products)
    save_sales(sales)

    return redirect(url_for("index"))


@app.route("/undo-last-sale", methods=["POST"])
def undo_last_sale():
    sales = load_sales()

    if not sales:
        return redirect(url_for("index"))

    last_sale = sales.pop()
    products = load_books()
    product = find_product_for_sale(products, last_sale)

    if product is not None:
        product["stock"] += normalize_sale(last_sale)["cantidad"]
        save_books(products)

    save_sales(sales)

    return redirect(url_for("index"))


@app.route("/reset-data", methods=["POST"])
def reset_data():
    save_sales([])

    if request.form.get("delete_products") == "yes":
        save_books([])

    return redirect(url_for("index"))


@app.route("/delete-product/<int:book_id>", methods=["POST"])
def delete_product(book_id):
    products = load_books()
    products = [product for product in products if product["id"] != book_id]
    save_books(products)

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
