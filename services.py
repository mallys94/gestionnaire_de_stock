from datetime import datetime

import pandas as pd
from sqlalchemy.exc import IntegrityError

from DBase import (
    SessionLocal, Product, Supplier, PurchaseOrder, PurchaseOrderItem,
    StockMovement, MovementType, OrderStatus, Sale, SaleStatus,
)


class StockService:
    """Business layer: every database operation used by the UI.

    All public methods that modify data return (success: bool, message: str)
    so the UI can react and inform the user instead of crashing.
    """

    REFUND_PERIOD_DAYS = 14

    # ------------------------------------------------------------------ #
    # Type-safe helpers (UI passes raw strings, numpy values, or numbers) #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_float(value, default=0.0):
        try:
            result = float(value)
            return default if result != result else result  # NaN guard
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _text(value, default=""):
        if value is None:
            return default
        if isinstance(value, float) and value != value:  # NaN guard
            return default
        return str(value).strip()

    # ------------------------------------------------------------------ #
    # Stock movements                                                     #
    # ------------------------------------------------------------------ #
    @staticmethod
    def log_movement(db, product_id, m_type, qty, ref=""):
        db.add(StockMovement(
            product_id=product_id,
            type=m_type,
            quantity=qty,
            reference=ref,
            created_at=datetime.now(),
        ))

    # ------------------------------------------------------------------ #
    # Products                                                            #
    # ------------------------------------------------------------------ #
    @staticmethod
    def add_or_update_product(data: dict):
        """Create a new product or update an existing one.

        ``data`` may contain ``product_id`` (update by ID, SKU rename allowed)
        or just ``sku`` (create / update by SKU). Every value is validated.
        """
        db = SessionLocal()
        try:
            sku = StockService._text(data.get("sku"))
            name = StockService._text(data.get("name"))
            if not sku or not name:
                return False, "SKU and Product Name are mandatory."

            quantity = StockService._to_int(data.get("quantity"), 0)
            if quantity < 0:
                return False, "Stock quantity cannot be negative."
            min_threshold = StockService._to_int(data.get("min_threshold"), 5)
            purchase_price = max(0.0, StockService._to_float(data.get("purchase_price_excl_tax")))
            selling_price = max(0.0, StockService._to_float(data.get("selling_price_excl_tax")))
            vat_rate = max(0.0, StockService._to_float(data.get("vat_rate"), 20.0))
            category = StockService._text(data.get("category"), "General")
            location = StockService._text(data.get("location"), "A-01")
            product_id = StockService._to_int(data.get("product_id"), None) or None

            prod = None
            if product_id:
                prod = db.query(Product).filter(Product.id == product_id).first()
                if not prod:
                    return False, "Product not found in database."
            else:
                prod = db.query(Product).filter(Product.sku == sku).first()

            if not prod:
                duplicate = db.query(Product).filter(Product.sku == sku).first()
                if duplicate:
                    return False, f"SKU '{sku}' is already used by product '{duplicate.name}'."
                prod = Product(
                    sku=sku, name=name, category=category, quantity=quantity,
                    min_threshold=min_threshold,
                    purchase_price_excl_tax=purchase_price,
                    selling_price_excl_tax=selling_price,
                    vat_rate=vat_rate, location=location,
                    supplier_id=data.get("supplier_id"),
                )
                db.add(prod)
                db.commit()
                db.refresh(prod)
                if prod.quantity > 0:
                    StockService.log_movement(db, prod.id, MovementType.INBOUND, prod.quantity, "Initial Stock")
                    db.commit()
                return True, f"Product '{name}' added successfully."
            else:
                if prod.sku != sku:
                    duplicate = db.query(Product).filter(
                        Product.sku == sku, Product.id != prod.id
                    ).first()
                    if duplicate:
                        return False, f"SKU '{sku}' is already used by product '{duplicate.name}'."

                old_qty = prod.quantity
                prod.sku = sku
                prod.name = name
                prod.category = category
                prod.quantity = quantity
                prod.min_threshold = min_threshold
                prod.purchase_price_excl_tax = purchase_price
                prod.selling_price_excl_tax = selling_price
                if data.get("vat_rate") not in (None, ""):
                    prod.vat_rate = vat_rate
                prod.location = location

                diff = quantity - old_qty
                if diff != 0:
                    m_type = MovementType.INBOUND if diff > 0 else MovementType.OUTBOUND
                    StockService.log_movement(db, prod.id, m_type, abs(diff), "Direct Update")
                db.commit()
                return True, f"Product '{name}' updated successfully."
        except Exception as e:
            db.rollback()
            return False, f"Could not save product: {e}"
        finally:
            db.close()

    @staticmethod
    def delete_product(product_id: int):
        """Permanently delete a product, but block it while referenced by orders."""
        db = SessionLocal()
        try:
            prod = db.query(Product).filter(Product.id == product_id).first()
            if not prod:
                return False, "Product not found."

            refs = db.query(PurchaseOrderItem).filter(
                PurchaseOrderItem.product_id == product_id
            ).count()
            sale_refs = db.query(Sale).filter(Sale.product_id == product_id).count()
            if refs or sale_refs:
                linked = []
                if refs:
                    linked.append(f"{refs} purchase order item(s)")
                if sale_refs:
                    linked.append(f"{sale_refs} sale(s)")
                return False, (
                    f"Product '{prod.name}' is referenced by {', '.join(linked)}.\n"
                    "Delete the related records first."
                )

            db.delete(prod)
            db.commit()
            return True, f"Product '{prod.name}' deleted permanently from database."
        except IntegrityError:
            db.rollback()
            return False, "Product could not be deleted because it is referenced by other records."
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Suppliers                                                           #
    # ------------------------------------------------------------------ #
    @staticmethod
    def add_supplier(code, name, contact="", email="", phone=""):
        db = SessionLocal()
        try:
            code = StockService._text(code)
            name = StockService._text(name)
            if not code or not name:
                return False, "Supplier code and company name are mandatory."
            if db.query(Supplier).filter(Supplier.code == code).first():
                return False, f"Supplier code '{code}' already exists."
            db.add(Supplier(
                code=code, name=name,
                contact_person=StockService._text(contact),
                email=StockService._text(email),
                phone=StockService._text(phone),
            ))
            db.commit()
            return True, f"Supplier '{name}' added successfully."
        except IntegrityError:
            db.rollback()
            return False, f"Supplier code '{code}' already exists."
        finally:
            db.close()

    @staticmethod
    def update_supplier(supplier_id, code, name, contact="", email="", phone=""):
        db = SessionLocal()
        try:
            sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
            if not sup:
                return False, "Supplier not found."
            code = StockService._text(code)
            name = StockService._text(name)
            if not code or not name:
                return False, "Supplier code and company name are mandatory."
            duplicate = db.query(Supplier).filter(
                Supplier.code == code, Supplier.id != supplier_id
            ).first()
            if duplicate:
                return False, f"Supplier code '{code}' is already used by another supplier."
            sup.code = code
            sup.name = name
            sup.contact_person = StockService._text(contact)
            sup.email = StockService._text(email)
            sup.phone = StockService._text(phone)
            db.commit()
            return True, f"Supplier '{name}' updated successfully."
        except Exception as e:
            db.rollback()
            return False, f"Could not update supplier: {e}"
        finally:
            db.close()

    @staticmethod
    def delete_supplier(supplier_id):
        db = SessionLocal()
        try:
            sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
            if not sup:
                return False, "Supplier not found."
            products = db.query(Product).filter(Product.supplier_id == supplier_id).count()
            orders = db.query(PurchaseOrder).filter(PurchaseOrder.supplier_id == supplier_id).count()
            if products or orders:
                return False, (
                    f"Supplier '{sup.name}' cannot be deleted: linked to {products} product(s) "
                    f"and {orders} order(s). Reassign or remove them first."
                )
            db.delete(sup)
            db.commit()
            return True, f"Supplier '{sup.name}' deleted permanently."
        except IntegrityError:
            db.rollback()
            return False, "Supplier could not be deleted because it is referenced by other records."
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Purchase orders                                                     #
    # ------------------------------------------------------------------ #
    @staticmethod
    def create_order(reference, supplier_id, items, vat_rate=20.0):
        """Create a purchase order. ``items`` is a list of
        ``{"product_id": int, "quantity": int}`` dicts."""
        db = SessionLocal()
        try:
            reference = StockService._text(reference)
            if not reference:
                return False, "Order reference cannot be empty."
            if not items:
                return False, "Order must contain at least one item."
            if not db.query(Supplier).filter(Supplier.id == supplier_id).first():
                return False, "Selected supplier no longer exists."
            if db.query(PurchaseOrder).filter(PurchaseOrder.reference == reference).first():
                return False, f"An order with reference '{reference}' already exists."

            parsed = []
            total_ht = 0.0
            for entry in items:
                product = db.query(Product).filter(Product.id == entry.get("product_id")).first()
                if not product:
                    return False, f"Product #{entry.get('product_id')} no longer exists."
                qty = max(1, StockService._to_int(entry.get("quantity"), 1))
                unit_cost = StockService._to_float(product.purchase_price_excl_tax)
                parsed.append((product.id, qty, unit_cost))
                total_ht += unit_cost * qty

            order = PurchaseOrder(
                reference=reference, supplier_id=supplier_id,
                status=OrderStatus.ORDERED, total_excl_tax=total_ht, vat_rate=vat_rate,
            )
            db.add(order)
            db.flush()
            for product_id, qty, unit_cost in parsed:
                db.add(PurchaseOrderItem(
                    order_id=order.id, product_id=product_id,
                    quantity_ordered=qty, unit_cost_excl_tax=unit_cost,
                ))
            db.commit()
            return True, f"Purchase Order '{reference}' created successfully."
        except IntegrityError:
            db.rollback()
            return False, f"An order with reference '{reference}' already exists."
        except Exception as e:
            db.rollback()
            return False, f"Could not save order: {e}"
        finally:
            db.close()

    @staticmethod
    def receive_order(order_id: int):
        db = SessionLocal()
        try:
            order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
            if not order:
                return False, "Order not found."
            if order.status == OrderStatus.RECEIVED:
                return False, "Order has already been received."
            if order.status == OrderStatus.CANCELLED:
                return False, "Cannot receive a cancelled order."
            if not order.items:
                return False, f"Order '{order.reference}' has no items and cannot be received."

            for item in order.items:
                product = db.query(Product).filter(Product.id == item.product_id).first()
                if product:
                    product.quantity += item.quantity_ordered
                    StockService.log_movement(
                        db, product.id, MovementType.ORDER_RECEIPT,
                        item.quantity_ordered, f"Received Order {order.reference}",
                    )

            order.total_excl_tax = sum(
                (i.quantity_ordered or 0) * (i.unit_cost_excl_tax or 0.0)
                for i in order.items
            )
            order.status = OrderStatus.RECEIVED
            db.commit()
            return True, "Order received and stock updated!"
        except Exception as e:
            db.rollback()
            return False, f"Could not receive order: {e}"
        finally:
            db.close()

    @staticmethod
    def cancel_or_return_order(order_id: int):
        """Cancel an order; if it was already received, deduct stock again."""
        db = SessionLocal()
        try:
            order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
            if not order:
                return False, "Order not found."
            if order.status == OrderStatus.CANCELLED:
                return False, "Order is already cancelled."

            if order.status == OrderStatus.RECEIVED:
                for item in order.items:
                    product = db.query(Product).filter(Product.id == item.product_id).first()
                    if product:
                        product.quantity = max(0, product.quantity - item.quantity_ordered)
                        StockService.log_movement(
                            db, product.id, MovementType.SUPPLIER_RETURN,
                            item.quantity_ordered, f"Return/Cancellation Order {order.reference}",
                        )
                msg = "Order cancelled! Stock deducted (Supplier Return)."
            else:
                msg = "Order cancelled successfully!"

            order.status = OrderStatus.CANCELLED
            db.commit()
            return True, msg
        except Exception as e:
            db.rollback()
            return False, f"Could not cancel order: {e}"
        finally:
            db.close()

    @staticmethod
    def delete_order_permanently(order_id: int, revert_stock: bool = True):
        """Permanently delete an order; optionally revert the stock it added."""
        db = SessionLocal()
        try:
            order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
            if not order:
                return False, "Order not found."

            if order.status == OrderStatus.RECEIVED and revert_stock:
                for item in order.items:
                    product = db.query(Product).filter(Product.id == item.product_id).first()
                    if product:
                        product.quantity = max(0, product.quantity - item.quantity_ordered)
                        StockService.log_movement(
                            db, product.id, MovementType.ADJUSTMENT,
                            item.quantity_ordered, f"Order {order.reference} Permanently Deleted",
                        )

            db.delete(order)
            db.commit()
            return True, f"Order '{order.reference}' permanently deleted from database."
        except IntegrityError:
            db.rollback()
            return False, "Order could not be deleted because it is referenced by other records."
        except Exception as e:
            db.rollback()
            return False, f"Could not delete order: {e}"
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Sales & refunds (return within 14 days)                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def create_sale(reference, product_id, quantity, unit_price=None, vat_rate=20.0):
        """Record a sale: validates stock, deducts quantity, logs a SALE movement."""
        db = SessionLocal()
        try:
            reference = StockService._text(reference)
            if not reference:
                return False, "Sale reference cannot be empty."
            qty = StockService._to_int(quantity)
            if qty <= 0:
                return False, "Sale quantity must be greater than zero."
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                return False, "Product not found."
            if (product.quantity or 0) < qty:
                return False, (
                    f"Insufficient stock for '{product.name}' "
                    f"(available: {product.quantity or 0}, requested: {qty})."
                )
            if db.query(Sale).filter(Sale.reference == reference).first():
                return False, f"A sale with reference '{reference}' already exists."

            unit_price = max(0.0, StockService._to_float(unit_price, product.selling_price_excl_tax or 0.0))
            vat_rate = max(0.0, StockService._to_float(vat_rate, 20.0))

            product.quantity -= qty
            total_ht = unit_price * qty
            sale = Sale(
                reference=reference, product_id=product.id, quantity=qty,
                unit_price_excl_tax=unit_price, vat_rate=vat_rate,
                total_excl_tax=total_ht, status=SaleStatus.SOLD,
            )
            db.add(sale)
            StockService.log_movement(db, product.id, MovementType.SALE, qty, f"Sale {reference}")
            db.commit()
            return True, f"Sale '{reference}' recorded: {qty} x '{product.name}', stock deducted."
        except IntegrityError:
            db.rollback()
            return False, f"A sale with reference '{reference}' already exists."
        except Exception as e:
            db.rollback()
            return False, f"Could not record sale: {e}"
        finally:
            db.close()

    @staticmethod
    def refund_sale(sale_id: int):
        """Refund a sale, only within the 14-day return window.

        Restores stock and logs a SALE REFUND movement.
        """
        db = SessionLocal()
        try:
            sale = db.query(Sale).filter(Sale.id == sale_id).first()
            if not sale:
                return False, "Sale not found."
            if sale.status == SaleStatus.REFUNDED:
                return False, "This sale has already been refunded."

            days = (datetime.now() - sale.sale_date).days if sale.sale_date else None
            if days is None or days > StockService.REFUND_PERIOD_DAYS:
                return False, (
                    f"Refund window exceeded: this sale is more than "
                    f"{StockService.REFUND_PERIOD_DAYS} days old.\n"
                    "Returns are only accepted within 14 days of the sale."
                )

            product = db.query(Product).filter(Product.id == sale.product_id).first()
            if product:
                product.quantity += sale.quantity
                StockService.log_movement(
                    db, product.id, MovementType.SALE_REFUND,
                    sale.quantity, f"Refund {sale.reference}",
                )
            sale.status = SaleStatus.REFUNDED
            sale.refund_date = datetime.now()
            db.commit()
            return True, f"Sale '{sale.reference}' refunded. Stock restored."
        except Exception as e:
            db.rollback()
            return False, f"Could not refund sale: {e}"
        finally:
            db.close()

    @staticmethod
    def delete_sale_permanently(sale_id: int, revert_stock: bool = True):
        """Permanently delete a sale; restore stock if it was still SOLD."""
        db = SessionLocal()
        try:
            sale = db.query(Sale).filter(Sale.id == sale_id).first()
            if not sale:
                return False, "Sale not found."

            if sale.status == SaleStatus.SOLD and revert_stock:
                product = db.query(Product).filter(Product.id == sale.product_id).first()
                if product:
                    product.quantity += sale.quantity
                    StockService.log_movement(
                        db, product.id, MovementType.ADJUSTMENT,
                        sale.quantity, f"Sale {sale.reference} Permanently Deleted",
                    )

            db.delete(sale)
            db.commit()
            return True, f"Sale '{sale.reference}' permanently deleted from database."
        except IntegrityError:
            db.rollback()
            return False, "Sale could not be deleted because it is referenced by other records."
        except Exception as e:
            db.rollback()
            return False, f"Could not delete sale: {e}"
        finally:
            db.close()

    @staticmethod
    def get_sales_summary() -> dict:
        db = SessionLocal()
        try:
            sales = db.query(Sale).all()
            sold_ttc = 0.0
            refunded_ttc = 0.0
            sold_count = refunded_count = 0
            for s in sales:
                total_ttc = (s.total_excl_tax or 0.0) * (1 + (s.vat_rate or 20.0) / 100.0)
                if s.status == SaleStatus.REFUNDED:
                    refunded_ttc += total_ttc
                    refunded_count += 1
                else:
                    sold_ttc += total_ttc
                    sold_count += 1
            return {
                "count": len(sales),
                "sold_count": sold_count,
                "refunded_count": refunded_count,
                "total_sold_ttc": sold_ttc,
                "total_refunded_ttc": refunded_ttc,
            }
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Stock adjustments & reporting                                       #
    # ------------------------------------------------------------------ #
    @staticmethod
    def adjust_stock(product_id, delta, reason=""):
        """Manually add (positive) or remove (negative) stock."""
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                return False, "Product not found."
            delta = StockService._to_int(delta)
            if delta == 0:
                return False, "Quantity change must be a non-zero number (e.g. +10 or -5)."
            product.quantity = max(0, product.quantity + delta)
            m_type = MovementType.INBOUND if delta > 0 else MovementType.OUTBOUND
            StockService.log_movement(
                db, product.id, m_type, abs(delta),
                StockService._text(reason, "Manual Adjustment"),
            )
            db.commit()
            return True, (
                f"Stock adjusted ({'+' if delta > 0 else ''}{delta}). "
                f"New stock for '{product.name}': {product.quantity}."
            )
        except Exception as e:
            db.rollback()
            return False, f"Could not adjust stock: {e}"
        finally:
            db.close()

    @staticmethod
    def get_inventory_summary() -> dict:
        db = SessionLocal()
        try:
            products = db.query(Product).all()
            total_value_ttc = 0.0
            low_stock = 0
            for p in products:
                qty = p.quantity or 0
                price = p.selling_price_excl_tax or 0.0
                vat = (p.vat_rate or 20.0) / 100.0
                total_value_ttc += qty * price * (1 + vat)
                if qty <= (p.min_threshold or 0):
                    low_stock += 1
            return {
                "count": len(products),
                "total_value_ttc": total_value_ttc,
                "low_stock": low_stock,
            }
        finally:
            db.close()

    @staticmethod
    def get_order_details(order_id: int):
        """Return a readable dict for one order, or None if not found."""
        db = SessionLocal()
        try:
            order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
            if not order:
                return None
            items = []
            for item in order.items:
                product = item.product
                unit_cost = item.unit_cost_excl_tax or 0.0
                items.append({
                    "sku": product.sku if product else "N/A",
                    "name": product.name if product else "Unknown product",
                    "quantity": item.quantity_ordered,
                    "unit_cost": unit_cost,
                    "line_total": unit_cost * (item.quantity_ordered or 0),
                })
            return {
                "reference": order.reference,
                "status": order.status,
                "total_excl_tax": order.total_excl_tax or 0.0,
                "vat_rate": order.vat_rate or 20.0,
                "items": items,
            }
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Excel import / export                                               #
    # ------------------------------------------------------------------ #
    @staticmethod
    def export_inventory_to_excel(file_path: str):
        db = SessionLocal()
        try:
            products = db.query(Product).order_by(Product.sku).all()
            data = []
            for p in products:
                selling_ht = p.selling_price_excl_tax or 0.0
                vat_rate = p.vat_rate or 20.0
                vat_amount = selling_ht * (vat_rate / 100.0)
                data.append({
                    "SKU": p.sku,
                    "Name": p.name,
                    "Category": p.category or "",
                    "Stock Qty": p.quantity or 0,
                    "Min Threshold": p.min_threshold or 0,
                    "Purchase Price Excl. Tax ($)": round(p.purchase_price_excl_tax or 0.0, 2),
                    "Selling Price Excl. Tax ($)": round(selling_ht, 2),
                    "VAT Rate (%)": vat_rate,
                    "VAT Amount ($)": round(vat_amount, 2),
                    "Selling Price Incl. Tax ($)": round(selling_ht + vat_amount, 2),
                    "Location": p.location or "",
                    "Supplier": p.supplier.name if p.supplier else "N/A",
                    "Status": "OK" if (p.quantity or 0) > (p.min_threshold or 0) else "LOW STOCK",
                })
            if not file_path.lower().endswith(".xlsx"):
                file_path += ".xlsx"
            pd.DataFrame(data).to_excel(file_path, index=False, engine="openpyxl")
            return True, f"Exported {len(products)} product(s) to Excel."
        except Exception as e:
            return False, f"Export failed: {e}"
        finally:
            db.close()

    REQUIRED_COLUMNS = ["SKU", "Name"]

    @staticmethod
    def import_inventory_from_excel(file_path: str):
        db = SessionLocal()
        try:
            df = pd.read_excel(file_path)
            missing = [c for c in StockService.REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                return False, f"Excel file is missing required column(s): {', '.join(missing)}."

            has_stock_qty = "Stock Qty" in df.columns
            added = updated = 0
            for _, row in df.iterrows():
                sku = StockService._text(row.get("SKU"))
                if not sku:
                    continue
                name = StockService._text(row.get("Name"), "Unnamed Product")

                def txt(key, default=""):
                    return StockService._text(row.get(key), default)

                quantity = max(0, StockService._to_int(row.get("Stock Qty"), 0)) if has_stock_qty else None
                min_threshold = max(0, StockService._to_int(row.get("Min Threshold"), 5))
                purchase_price = max(0.0, StockService._to_float(row.get("Purchase Price Excl. Tax ($)")))
                selling_price = max(0.0, StockService._to_float(row.get("Selling Price Excl. Tax ($)")))
                vat_rate = max(0.0, StockService._to_float(row.get("VAT Rate (%)"), 20.0))

                prod = db.query(Product).filter(Product.sku == sku).first()
                if not prod:
                    prod = Product(
                        sku=sku, name=name, category=txt("Category", "General"),
                        quantity=quantity or 0, min_threshold=min_threshold,
                        purchase_price_excl_tax=purchase_price,
                        selling_price_excl_tax=selling_price,
                        vat_rate=vat_rate,
                        location=txt("Location", "A-01"),
                    )
                    db.add(prod)
                    db.flush()
                    added += 1
                    if prod.quantity > 0:
                        StockService.log_movement(db, prod.id, MovementType.INBOUND, prod.quantity, "Excel Import")
                else:
                    old_qty = prod.quantity
                    prod.name = name
                    prod.category = txt("Category", prod.category)
                    if quantity is not None:
                        prod.quantity = quantity
                    prod.min_threshold = min_threshold
                    prod.purchase_price_excl_tax = purchase_price
                    prod.selling_price_excl_tax = selling_price
                    prod.vat_rate = vat_rate
                    prod.location = txt("Location", prod.location)
                    updated += 1
                    diff = prod.quantity - old_qty
                    if diff != 0:
                        m_type = MovementType.INBOUND if diff > 0 else MovementType.OUTBOUND
                        StockService.log_movement(db, prod.id, m_type, abs(diff), "Excel Import")

            db.commit()
            return True, f"Import finished: {added} product(s) added, {updated} updated."
        except FileNotFoundError:
            return False, "Excel file not found."
        except Exception as e:
            db.rollback()
            return False, f"Import failed: {e}"
        finally:
            db.close()
