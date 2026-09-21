from datetime import datetime, date, time

import pandas as pd
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from DBase import (
    SessionLocal, Product, Supplier, Customer, PurchaseOrder, PurchaseOrderItem,
    StockMovement, MovementType, OrderStatus, Sale, SaleStatus,
)
from i18n import tr


def _window_start(dt):
    day = dt.date() if isinstance(dt, datetime) else dt
    return datetime.combine(day, time.min)


def _window_end(dt):
    day = dt.date() if isinstance(dt, datetime) else dt
    return datetime.combine(day, time.max)


class StockService:
    """Business layer: every database operation used by the UI.

    All public methods that modify data return (success: bool, message: str)
    so the UI can react and inform the user instead of crashing.

    User-facing messages and movement references are localized through the
    i18n module, so they follow the currently selected UI language.
    """

    REFUND_PERIOD_DAYS = 14

    # Payment statuses
    PAYMENT_PAID = "PAID"
    PAYMENT_CREDIT = "CREDIT"    # sale on credit -> unpaid / outbound pending
    PAYMENT_PENDING = "PENDING"  # purchase order not paid yet

    @staticmethod
    def _ttc(total_excl_tax, vat_rate):
        return (total_excl_tax or 0.0) * (1 + (vat_rate or 20.0) / 100.0)

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
                return False, tr("svc.sku_name_required")

            quantity = StockService._to_int(data.get("quantity"), 0)
            if quantity < 0:
                return False, tr("svc.stock_not_negative")
            min_threshold = StockService._to_int(data.get("min_threshold"), 5)
            purchase_price = max(0.0, StockService._to_float(data.get("purchase_price_excl_tax")))
            selling_price = max(0.0, StockService._to_float(data.get("selling_price_excl_tax")))
            vat_rate = max(0.0, StockService._to_float(data.get("vat_rate"), 20.0))
            category = StockService._text(data.get("category"), tr("dlg.default_category"))
            location = StockService._text(data.get("location"), tr("dlg.default_location"))
            product_id = StockService._to_int(data.get("product_id"), None) or None

            prod = None
            if product_id:
                prod = db.query(Product).filter(Product.id == product_id).first()
                if not prod:
                    return False, tr("svc.product_not_found_db")
            else:
                prod = db.query(Product).filter(Product.sku == sku).first()

            if not prod:
                duplicate = db.query(Product).filter(Product.sku == sku).first()
                if duplicate:
                    return False, tr("svc.sku_used", sku=sku, name=duplicate.name)
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
                    StockService.log_movement(
                        db, prod.id, MovementType.INBOUND, prod.quantity,
                        tr("mov.ref.initial_stock"),
                    )
                    db.commit()
                return True, tr("svc.product_added", name=name)
            else:
                if prod.sku != sku:
                    duplicate = db.query(Product).filter(
                        Product.sku == sku, Product.id != prod.id
                    ).first()
                    if duplicate:
                        return False, tr("svc.sku_used", sku=sku, name=duplicate.name)

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
                    StockService.log_movement(
                        db, prod.id, m_type, abs(diff), tr("mov.ref.direct_update")
                    )
                db.commit()
                return True, tr("svc.product_updated", name=name)
        except Exception as e:
            db.rollback()
            return False, tr("svc.product_save_error", error=e)
        finally:
            db.close()

    @staticmethod
    def delete_product(product_id: int):
        """Permanently delete a product, but block it while referenced by orders."""
        db = SessionLocal()
        try:
            prod = db.query(Product).filter(Product.id == product_id).first()
            if not prod:
                return False, tr("svc.product_not_found")

            refs = db.query(PurchaseOrderItem).filter(
                PurchaseOrderItem.product_id == product_id
            ).count()
            sale_refs = db.query(Sale).filter(Sale.product_id == product_id).count()
            if refs or sale_refs:
                linked = []
                if refs:
                    linked.append(f"{refs} {tr('svc.link_item')}")
                if sale_refs:
                    linked.append(f"{sale_refs} {tr('svc.link_sale')}")
                return False, tr(
                    "svc.product_referenced",
                    name=prod.name,
                    links=", ".join(linked),
                )

            db.delete(prod)
            db.commit()
            return True, tr("svc.product_deleted", name=prod.name)
        except IntegrityError:
            db.rollback()
            return False, tr("svc.product_ref_error")
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
                return False, tr("svc.supplier_mandatory")
            if db.query(Supplier).filter(Supplier.code == code).first():
                return False, tr("svc.supplier_code_exists", code=code)
            db.add(Supplier(
                code=code, name=name,
                contact_person=StockService._text(contact),
                email=StockService._text(email),
                phone=StockService._text(phone),
            ))
            db.commit()
            return True, tr("svc.supplier_added", name=name)
        except IntegrityError:
            db.rollback()
            return False, tr("svc.supplier_code_exists", code=code)
        finally:
            db.close()

    @staticmethod
    def update_supplier(supplier_id, code, name, contact="", email="", phone=""):
        db = SessionLocal()
        try:
            sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
            if not sup:
                return False, tr("svc.supplier_not_found")
            code = StockService._text(code)
            name = StockService._text(name)
            if not code or not name:
                return False, tr("svc.supplier_mandatory")
            duplicate = db.query(Supplier).filter(
                Supplier.code == code, Supplier.id != supplier_id
            ).first()
            if duplicate:
                return False, tr("svc.supplier_code_used", code=code)
            sup.code = code
            sup.name = name
            sup.contact_person = StockService._text(contact)
            sup.email = StockService._text(email)
            sup.phone = StockService._text(phone)
            db.commit()
            return True, tr("svc.supplier_updated", name=name)
        except Exception as e:
            db.rollback()
            return False, tr("svc.supplier_update_error", error=e)
        finally:
            db.close()

    @staticmethod
    def delete_supplier(supplier_id):
        db = SessionLocal()
        try:
            sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
            if not sup:
                return False, tr("svc.supplier_not_found")
            products = db.query(Product).filter(Product.supplier_id == supplier_id).count()
            orders = db.query(PurchaseOrder).filter(PurchaseOrder.supplier_id == supplier_id).count()
            if products or orders:
                return False, tr(
                    "svc.supplier_delete_blocked",
                    name=sup.name,
                    products=products,
                    orders=orders,
                )
            db.delete(sup)
            db.commit()
            return True, tr("svc.supplier_deleted", name=sup.name)
        except IntegrityError:
            db.rollback()
            return False, tr("svc.supplier_ref_error")
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Customers                                                           #
    # ------------------------------------------------------------------ #
    @staticmethod
    def next_customer_code():
        """Return the next sequential customer code, e.g. '0001', '0002'..."""
        db = SessionLocal()
        try:
            max_n = 0
            for c in db.query(Customer.code).all():
                code = (c[0] or "").strip()
                if code.isdigit():
                    max_n = max(max_n, int(code))
            return f"{max_n + 1:04d}"
        finally:
            db.close()

    @staticmethod
    def add_customer(code, name, contact="", email="", phone=""):
        db = SessionLocal()
        try:
            name = StockService._text(name)
            if not name:
                return False, tr("svc.customer_mandatory")
            code = StockService._text(code) or StockService.next_customer_code()
            if db.query(Customer).filter(Customer.code == code).first():
                return False, tr("svc.customer_code_exists", code=code)
            db.add(Customer(
                code=code, name=name,
                contact_person=StockService._text(contact),
                email=StockService._text(email),
                phone=StockService._text(phone),
            ))
            db.commit()
            return True, tr("svc.customer_added", name=name)
        except IntegrityError:
            db.rollback()
            return False, tr("svc.customer_code_exists", code=code)
        finally:
            db.close()

    @staticmethod
    def update_customer(customer_id, code, name, contact="", email="", phone=""):
        db = SessionLocal()
        try:
            cust = db.query(Customer).filter(Customer.id == customer_id).first()
            if not cust:
                return False, tr("svc.customer_not_found")
            code = StockService._text(code)
            name = StockService._text(name)
            if not code or not name:
                return False, tr("svc.customer_mandatory")
            duplicate = db.query(Customer).filter(
                Customer.code == code, Customer.id != customer_id
            ).first()
            if duplicate:
                return False, tr("svc.customer_code_used", code=code)
            cust.code = code
            cust.name = name
            cust.contact_person = StockService._text(contact)
            cust.email = StockService._text(email)
            cust.phone = StockService._text(phone)
            db.commit()
            return True, tr("svc.customer_updated", name=name)
        except Exception as e:
            db.rollback()
            return False, tr("svc.customer_update_error", error=e)
        finally:
            db.close()

    @staticmethod
    def delete_customer(customer_id):
        db = SessionLocal()
        try:
            cust = db.query(Customer).filter(Customer.id == customer_id).first()
            if not cust:
                return False, tr("svc.customer_not_found")
            sales = db.query(Sale).filter(Sale.customer_id == customer_id).count()
            if sales:
                return False, tr(
                    "svc.customer_delete_blocked", name=cust.name, sales=sales
                )
            db.delete(cust)
            db.commit()
            return True, tr("svc.customer_deleted", name=cust.name)
        except IntegrityError:
            db.rollback()
            return False, tr("svc.customer_ref_error")
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Purchase orders                                                     #
    # ------------------------------------------------------------------ #
    @staticmethod
    def create_order(reference, supplier_id, items, vat_rate=20.0, payment_status="PAID"):
        """Create a purchase order. ``items`` is a list of dicts:
        ``{"product_id": int, "quantity": int, "unit_price": float (optional)}``.

        The ordered quantities are added to stock immediately (an order counts
        as stock-in from the moment it is created), one INBOUND movement per
        line is logged, so stock log totals stay consistent.
        """
        db = SessionLocal()
        try:
            reference = StockService._text(reference)
            if not reference:
                return False, tr("svc.order_ref_empty")
            if not items:
                return False, tr("svc.order_no_items")
            if not db.query(Supplier).filter(Supplier.id == supplier_id).first():
                return False, tr("svc.supplier_gone")
            if db.query(PurchaseOrder).filter(PurchaseOrder.reference == reference).first():
                return False, tr("svc.order_ref_exists", ref=reference)

            parsed = []
            total_ht = 0.0
            for entry in items:
                product = db.query(Product).filter(Product.id == entry.get("product_id")).first()
                if not product:
                    return False, tr("svc.product_gone", pid=entry.get("product_id"))
                qty = max(1, StockService._to_int(entry.get("quantity"), 1))
                unit_cost = StockService._to_float(
                    entry.get("unit_price"), product.purchase_price_excl_tax
                )
                parsed.append((product.id, qty, unit_cost))
                total_ht += unit_cost * qty

            order = PurchaseOrder(
                reference=reference, supplier_id=supplier_id,
                status=OrderStatus.ORDERED, total_excl_tax=total_ht, vat_rate=vat_rate,
                payment_status=(
                    payment_status if payment_status in (
                        StockService.PAYMENT_PAID, StockService.PAYMENT_PENDING
                    ) else StockService.PAYMENT_PAID
                ),
            )
            db.add(order)
            db.flush()
            for product_id, qty, unit_cost in parsed:
                db.add(PurchaseOrderItem(
                    order_id=order.id, product_id=product_id,
                    quantity_ordered=qty, unit_cost_excl_tax=unit_cost,
                ))
                product = db.query(Product).filter(Product.id == product_id).first()
                if product:
                    product.quantity = (product.quantity or 0) + qty
                    StockService.log_movement(
                        db, product_id, MovementType.INBOUND, qty,
                        tr("mov.ref.order_created", ref=reference),
                    )
            db.commit()
            return True, tr("svc.order_created", ref=reference)
        except IntegrityError:
            db.rollback()
            return False, tr("svc.order_ref_exists", ref=reference)
        except Exception as e:
            db.rollback()
            return False, tr("svc.order_save_error", error=e)
        finally:
            db.close()

    @staticmethod
    def receive_order(order_id: int):
        """Mark an order as received. Stock was already added at creation, so
        receiving only finalizes the status (no double addition)."""
        db = SessionLocal()
        try:
            order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
            if not order:
                return False, tr("svc.order_not_found")
            if order.status == OrderStatus.RECEIVED:
                return False, tr("svc.order_already_received")
            if order.status == OrderStatus.CANCELLED:
                return False, tr("svc.order_cancelled_receive")
            if not order.items:
                return False, tr("svc.order_no_items_receive", ref=order.reference)

            order.total_excl_tax = sum(
                (i.quantity_ordered or 0) * (i.unit_cost_excl_tax or 0.0)
                for i in order.items
            )
            order.status = OrderStatus.RECEIVED
            db.commit()
            return True, tr("svc.order_received")
        except Exception as e:
            db.rollback()
            return False, tr("svc.order_receive_error", error=e)
        finally:
            db.close()

    @staticmethod
    def cancel_or_return_order(order_id: int):
        """Cancel an order. Since creation adds stock, any order that was not
        cancelled yet must have its stock deducted again."""
        db = SessionLocal()
        try:
            order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
            if not order:
                return False, tr("svc.order_not_found")
            if order.status == OrderStatus.CANCELLED:
                return False, tr("svc.order_already_cancelled")

            for item in order.items:
                product = db.query(Product).filter(Product.id == item.product_id).first()
                if product:
                    product.quantity = max(0, product.quantity - item.quantity_ordered)
                    StockService.log_movement(
                        db, product.id, MovementType.SUPPLIER_RETURN,
                        item.quantity_ordered,
                        tr("mov.ref.return_order", ref=order.reference),
                    )
            msg = tr("svc.order_cancelled_return")

            order.status = OrderStatus.CANCELLED
            db.commit()
            return True, msg
        except Exception as e:
            db.rollback()
            return False, tr("svc.order_cancel_error", error=e)
        finally:
            db.close()

    @staticmethod
    def delete_order_permanently(order_id: int, revert_stock: bool = True):
        """Permanently delete an order; unless it was already cancelled, revert
        the stock that was added when the order was created."""
        db = SessionLocal()
        try:
            order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
            if not order:
                return False, tr("svc.order_not_found")

            if order.status != OrderStatus.CANCELLED and revert_stock:
                for item in order.items:
                    product = db.query(Product).filter(Product.id == item.product_id).first()
                    if product:
                        product.quantity = max(0, product.quantity - item.quantity_ordered)
                        StockService.log_movement(
                            db, product.id, MovementType.SUPPLIER_RETURN,
                            item.quantity_ordered,
                            tr("mov.ref.order_deleted", ref=order.reference),
                        )

            db.delete(order)
            db.commit()
            return True, tr("svc.order_deleted", ref=order.reference)
        except IntegrityError:
            db.rollback()
            return False, tr("svc.order_ref_error")
        except Exception as e:
            db.rollback()
            return False, tr("svc.order_delete_error", error=e)
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Sales & refunds (return within 14 days)                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def create_sale(reference, product_id, quantity, unit_price=None, vat_rate=20.0,
                    customer_id=None, payment_status="PAID", sale_date=None, refundable=True):
        """Record a sale: validates stock, deducts quantity, logs a SALE movement.

        ``sale_date`` may be a date/datetime (defaults to now). ``refundable=False``
        marks the sale as final: no 14-day return window applies, so it is counted
        as confirmed revenue immediately.
        """
        db = SessionLocal()
        try:
            reference = StockService._text(reference)
            if not reference:
                return False, tr("svc.sale_ref_empty")
            qty = StockService._to_int(quantity)
            if qty <= 0:
                return False, tr("svc.sale_qty_positive")
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                return False, tr("svc.product_not_found")
            if (product.quantity or 0) < qty:
                return False, tr(
                    "svc.insufficient_stock",
                    name=product.name,
                    available=product.quantity or 0,
                    requested=qty,
                )
            if db.query(Sale).filter(Sale.reference == reference).first():
                return False, tr("svc.sale_ref_exists", ref=reference)

            customer_id = StockService._to_int(customer_id, None) or None
            if customer_id and not db.query(Customer).filter(Customer.id == customer_id).first():
                return False, tr("svc.customer_gone")

            if sale_date is None:
                sale_date = datetime.now()
            elif isinstance(sale_date, date) and not isinstance(sale_date, datetime):
                sale_date = datetime.combine(sale_date, datetime.min.time())
            if not isinstance(sale_date, datetime):
                return False, tr("svc.sale_date_invalid")
            if sale_date > datetime.now():
                return False, tr("svc.sale_date_future")

            unit_price = max(0.0, StockService._to_float(unit_price, product.selling_price_excl_tax or 0.0))
            vat_rate = max(0.0, StockService._to_float(vat_rate, 20.0))
            payment_status = (
                payment_status if payment_status in (
                    StockService.PAYMENT_PAID, StockService.PAYMENT_CREDIT
                ) else StockService.PAYMENT_PAID
            )

            product.quantity -= qty
            total_ht = unit_price * qty
            sale = Sale(
                reference=reference, product_id=product.id, quantity=qty,
                unit_price_excl_tax=unit_price, vat_rate=vat_rate,
                total_excl_tax=total_ht, status=SaleStatus.SOLD, sale_date=sale_date,
                customer_id=customer_id, payment_status=payment_status,
                refundable=bool(refundable),
            )
            db.add(sale)
            StockService.log_movement(
                db, product.id, MovementType.SALE, qty, tr("mov.ref.sale", ref=reference)
            )
            db.commit()
            return True, tr(
                "svc.sale_recorded",
                ref=reference, qty=qty, name=product.name,
            )
        except IntegrityError:
            db.rollback()
            return False, tr("svc.sale_ref_exists", ref=reference)
        except Exception as e:
            db.rollback()
            return False, tr("svc.sale_record_error", error=e)
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
                return False, tr("svc.sale_not_found")
            if sale.status == SaleStatus.REFUNDED:
                return False, tr("svc.sale_already_refunded")
            if sale.refundable is False:
                return False, tr("svc.sale_no_refund", ref=sale.reference)

            days = (datetime.now() - sale.sale_date).days if sale.sale_date else None
            if days is None or days > StockService.REFUND_PERIOD_DAYS:
                return False, tr("svc.refund_window", days=StockService.REFUND_PERIOD_DAYS)

            product = db.query(Product).filter(Product.id == sale.product_id).first()
            if product:
                product.quantity += sale.quantity
                StockService.log_movement(
                    db, product.id, MovementType.SALE_REFUND,
                    sale.quantity, tr("mov.ref.refund", ref=sale.reference),
                )
            sale.status = SaleStatus.REFUNDED
            sale.refund_date = datetime.now()
            db.commit()
            return True, tr("svc.sale_refunded", ref=sale.reference)
        except Exception as e:
            db.rollback()
            return False, tr("svc.sale_refund_error", error=e)
        finally:
            db.close()

    @staticmethod
    def mark_sale_paid(sale_id: int):
        """Mark a credit sale as paid (no longer part of outbound pending)."""
        db = SessionLocal()
        try:
            sale = db.query(Sale).filter(Sale.id == sale_id).first()
            if not sale:
                return False, tr("svc.sale_not_found")
            if sale.payment_status == StockService.PAYMENT_PAID:
                return False, tr("svc.sale_already_paid")
            sale.payment_status = StockService.PAYMENT_PAID
            db.commit()
            return True, tr("svc.sale_paid", ref=sale.reference)
        except Exception as e:
            db.rollback()
            return False, tr("svc.sale_pay_error", error=e)
        finally:
            db.close()

    @staticmethod
    def set_sale_final(sale_id: int, final: bool = True):
        """Toggle the 14-day refund window for a sale.

        ``final=True`` marks the sale as non-refundable so it is immediately
        counted as confirmed revenue (skips the refund window) in finance.
        """
        db = SessionLocal()
        try:
            sale = db.query(Sale).filter(Sale.id == sale_id).first()
            if not sale:
                return False, tr("svc.sale_not_found")
            if sale.status == SaleStatus.REFUNDED:
                return False, tr("svc.sale_already_refunded")
            sale.refundable = not bool(final)
            db.commit()
            if final:
                return True, tr("svc.sale_final_confirmed", ref=sale.reference)
            return True, tr("svc.sale_window_restored", ref=sale.reference)
        except Exception as e:
            db.rollback()
            return False, tr("svc.sale_final_error", error=e)
        finally:
            db.close()

    @staticmethod
    def delete_sale_permanently(sale_id: int, revert_stock: bool = True):
        """Permanently delete a sale; restore stock if it was still SOLD."""
        db = SessionLocal()
        try:
            sale = db.query(Sale).filter(Sale.id == sale_id).first()
            if not sale:
                return False, tr("svc.sale_not_found")

            if sale.status == SaleStatus.SOLD and revert_stock:
                product = db.query(Product).filter(Product.id == sale.product_id).first()
                if product:
                    product.quantity += sale.quantity
                    StockService.log_movement(
                        db, product.id, MovementType.ADJUSTMENT,
                        sale.quantity, tr("mov.ref.sale_deleted", ref=sale.reference),
                    )

            db.delete(sale)
            db.commit()
            return True, tr("svc.sale_deleted", ref=sale.reference)
        except IntegrityError:
            db.rollback()
            return False, tr("svc.sale_ref_error")
        except Exception as e:
            db.rollback()
            return False, tr("svc.sale_delete_error", error=e)
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
    def get_stock_log_summary() -> dict:
        """Aggregate figures for the Stock Log (movements) dashboard."""
        db = SessionLocal()
        try:
            total_movements = db.query(StockMovement).count()
            items_sold = db.query(Sale).filter(
                Sale.status != SaleStatus.REFUNDED
            ).with_entities(func.coalesce(func.sum(Sale.quantity), 0)).scalar() or 0
            items_adjusted = db.query(StockMovement).filter(
                StockMovement.type == MovementType.ADJUSTMENT
            ).with_entities(func.coalesce(func.sum(StockMovement.quantity), 0)).scalar() or 0

            stock_on_hand = int(sum(
                (p.quantity or 0) for p in db.query(Product).all()
            ))

            revenue_ttc = 0.0
            refunded_ttc = 0.0
            pending_ttc = 0.0
            sale_count = 0
            for s in db.query(Sale).all():
                total_ttc = StockService._ttc(s.total_excl_tax, s.vat_rate)
                if s.status == SaleStatus.REFUNDED:
                    refunded_ttc += total_ttc
                    continue
                sale_count += 1
                revenue_ttc += total_ttc
                if s.payment_status == StockService.PAYMENT_CREDIT:
                    pending_ttc += total_ttc
            return {
                "total_movements": total_movements,
                "items_sold": int(items_sold),
                "stock_on_hand": stock_on_hand,
                "items_adjusted": int(items_adjusted),
                "revenue_ttc": round(revenue_ttc, 2),
                "refunded_ttc": round(refunded_ttc, 2),
                "pending_ttc": round(pending_ttc, 2),
                "sale_count": sale_count,
            }
        finally:
            db.close()

    @staticmethod
    def adjust_stock(product_id, new_qty, reason=""):
        """Set the stock of a product to an exact, absolute quantity.

        The entered value becomes the new stock level (count-based, equal to what
        you see on the shelf). The difference vs. the previous stock is recorded
        as a movement, which avoids the miscalculations of delta-style entries.
        """
        db = SessionLocal()
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                return False, tr("svc.product_not_found")
            new_qty = StockService._to_int(new_qty)
            if new_qty < 0:
                return False, tr("svc.stock_not_negative")
            current = product.quantity or 0
            if new_qty == current:
                return False, tr("svc.adjust_unchanged", qty=current, name=product.name)
            delta = new_qty - current
            product.quantity = new_qty
            m_type = MovementType.INBOUND if delta > 0 else MovementType.OUTBOUND
            StockService.log_movement(
                db, product.id, m_type, abs(delta),
                StockService._text(reason, tr("adjust.default_reason")),
            )
            db.commit()
            return True, tr(
                "svc.stock_adjusted_to",
                name=product.name, qty=product.quantity,
                delta=f"{'+' if delta > 0 else ''}{delta}",
            )
        except Exception as e:
            db.rollback()
            return False, tr("svc.adjust_error", error=e)
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
                    "name": product.name if product else tr("status.unknown"),
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
            return True, tr("svc.export_ok", count=len(products))
        except Exception as e:
            return False, tr("svc.export_fail", error=e)
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
                return False, tr("svc.missing_columns", cols=", ".join(missing))

            has_stock_qty = "Stock Qty" in df.columns
            added = updated = 0
            for _, row in df.iterrows():
                sku = StockService._text(row.get("SKU"))
                if not sku:
                    continue
                name = StockService._text(row.get("Name"), tr("svc.unnamed_product"))

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
                        sku=sku, name=name, category=txt("Category", tr("dlg.default_category")),
                        quantity=quantity or 0, min_threshold=min_threshold,
                        purchase_price_excl_tax=purchase_price,
                        selling_price_excl_tax=selling_price,
                        vat_rate=vat_rate,
                        location=txt("Location", tr("dlg.default_location")),
                    )
                    db.add(prod)
                    db.flush()
                    added += 1
                    if prod.quantity > 0:
                        StockService.log_movement(
                            db, prod.id, MovementType.INBOUND, prod.quantity,
                            tr("mov.ref.excel_import"),
                        )
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
                        StockService.log_movement(
                            db, prod.id, m_type, abs(diff), tr("mov.ref.excel_import")
                        )

            db.commit()
            return True, tr("svc.import_ok", added=added, updated=updated)
        except FileNotFoundError:
            return False, tr("svc.file_not_found")
        except Exception as e:
            db.rollback()
            return False, tr("svc.import_fail", error=e)
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Finance                                                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def get_finance_data(from_date=None, to_date=None, partner_kind="all"):
        """Aggregate financial figures.

        - Revenue (net)   : non-refunded sales, incl. VAT
        - Pending refund  : those still inside the ``REFUND_PERIOD_DAYS`` window
        - Confirmed       : older than the window -> final revenue
        - Credit pending  : non-refunded sales still unpaid (on credit)
        - Inbound         : received purchase orders (money spent, incl. VAT)
        - Inbound pending : purchase orders ordered but not received yet
        - Orders unpaid   : purchase orders with a pending payment
        - Net result      : Confirmed revenue - Inbound (received)

        ``partner_kind`` filters the detail lines: "all" | "supplier" | "customer".
        Returns a dict with summary floats + ordered detail ``lines``.
        """
        db = SessionLocal()
        try:
            frm = _window_start(from_date) if from_date else None
            to = _window_end(to_date) if to_date else None

            def in_window(dt):
                if dt is None:
                    return frm is None and to is None
                if frm and dt < frm:
                    return False
                if to and dt > to:
                    return False
                return True

            revenue_gross = 0.0
            refunded = 0.0
            pending_refund = 0.0
            confirmed = 0.0
            credit_pending = 0.0
            now = datetime.now()

            for s in db.query(Sale).all():
                if not in_window(s.sale_date):
                    continue
                total_ttc = StockService._ttc(s.total_excl_tax, s.vat_rate)
                refunded_status = s.status == SaleStatus.REFUNDED
                refundable = s.refundable is not False
                if refunded_status:
                    refunded += total_ttc
                    continue
                revenue_gross += total_ttc

                days = (now - s.sale_date).days if s.sale_date else None
                in_refund_window = (
                    refundable and days is not None and 0 <= days <= StockService.REFUND_PERIOD_DAYS
                )
                if in_refund_window:
                    pending_refund += total_ttc
                else:
                    confirmed += total_ttc
                if s.payment_status == StockService.PAYMENT_CREDIT:
                    credit_pending += total_ttc

            inbound = 0.0
            inbound_pending = 0.0
            orders_unpaid = 0.0
            lines = []

            for o in db.query(PurchaseOrder).all():
                if o.status == OrderStatus.CANCELLED:
                    continue
                if not in_window(o.order_date):
                    continue
                total_ttc = StockService._ttc(o.total_excl_tax, o.vat_rate)
                received = o.status == OrderStatus.RECEIVED
                if received:
                    inbound += total_ttc
                else:
                    inbound_pending += total_ttc
                if o.payment_status != StockService.PAYMENT_PAID:
                    orders_unpaid += total_ttc
                lines.append({
                    "date": o.order_date,
                    "reference": o.reference,
                    "direction": "INBOUND",
                    "pending": not received,
                    "kind": "supplier",
                    "partner": o.supplier.name if o.supplier else "",
                    "amount": round(total_ttc, 2),
                    "note": o.status.name,
                })

            for s in db.query(Sale).all():
                if not in_window(s.sale_date):
                    continue
                total_ttc = StockService._ttc(s.total_excl_tax, s.vat_rate)
                refunded_status = s.status == SaleStatus.REFUNDED
                refundable = s.refundable is not False
                days = (now - s.sale_date).days if s.sale_date else None
                in_refund_window = (
                    not refunded_status and refundable and days is not None
                    and 0 <= days <= StockService.REFUND_PERIOD_DAYS
                )
                credit = (not refunded_status and s.payment_status == StockService.PAYMENT_CREDIT)
                lines.append({
                    "date": s.sale_date,
                    "reference": s.reference,
                    "direction": "OUTBOUND",
                    "pending": in_refund_window or credit,
                    "kind": "customer",
                    "partner": s.customer.name if s.customer else "",
                    "amount": round(total_ttc, 2),
                    "note": ("REFUNDED" if refunded_status else
                             ("CREDIT" if credit else ("WINDOW" if in_refund_window else "FINAL"))),
                })

            if partner_kind == "supplier":
                lines = [ln for ln in lines if ln["kind"] == "supplier"]
            elif partner_kind == "customer":
                lines = [ln for ln in lines if ln["kind"] == "customer"]

            lines.sort(key=lambda ln: ln["date"] or datetime.min, reverse=True)

            revenue_net = revenue_gross - refunded
            return {
                "revenue_gross": round(revenue_gross, 2),
                "revenue_net": round(revenue_net, 2),
                "refunded": round(refunded, 2),
                "pending_refund": round(pending_refund, 2),
                "confirmed": round(confirmed, 2),
                "credit_pending": round(credit_pending, 2),
                "inbound": round(inbound, 2),
                "inbound_pending": round(inbound_pending, 2),
                "orders_unpaid": round(orders_unpaid, 2),
                "net_result": round(confirmed - inbound, 2),
                "lines": lines,
            }
        finally:
            db.close()