import sys
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from DBase import (
    init_db, SessionLocal, Product, Supplier, PurchaseOrder,
    StockMovement, OrderStatus, Sale, SaleStatus,
)
from services import StockService

# Excel White Theme
STYLE_SHEET = """
QMainWindow {
    background-color: #f8f9fa;
}
QDialog {
    background-color: #f8f9fa;
}
QTabWidget::pane {
    border: 1px solid #d1d5db;
    background-color: #ffffff;
}
QTabBar::tab {
    background: #e5e7eb;
    color: #374151;
    padding: 8px 18px;
    font-weight: bold;
    border: 1px solid #d1d5db;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #107c41; /* Excel Green */
    border-top: 3px solid #107c41;
}
QTableWidget {
    background-color: #ffffff;
    color: #1f2937;
    gridline-color: #d1d5db;
    font-size: 13px;
    selection-background-color: #e8f5e9;
    selection-color: #000000;
}
QHeaderView::section {
    background-color: #f3f4f6;
    color: #111827;
    padding: 6px;
    font-weight: bold;
    border: 1px solid #d1d5db;
}
QPushButton {
    background-color: #107c41; /* Excel Green */
    color: #ffffff;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
    border: none;
}
QPushButton:hover {
    background-color: #0b582e;
}
QPushButton#btnDanger {
    background-color: #dc2626;
    color: #ffffff;
}
QPushButton#btnDanger:hover {
    background-color: #991b1b;
}
QLineEdit, QComboBox {
    background-color: #ffffff;
    color: #1f2937;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 6px;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #107c41;
}
QLabel#lblSummary {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 8px 12px;
    font-weight: bold;
    font-size: 13px;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Inventory & Purchase Order Manager (Excel White Theme)")
        self.resize(1300, 760)
        self.setStyleSheet(STYLE_SHEET)

        init_db()
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab 1: Inventory
        self.tab_inventory = QWidget()
        self.init_inventory_tab()
        self.tabs.addTab(self.tab_inventory, "Inventory & VAT")

        # Tab 2: Suppliers
        self.tab_suppliers = QWidget()
        self.init_suppliers_tab()
        self.tabs.addTab(self.tab_suppliers, "Suppliers")

        # Tab 3: Purchase Orders
        self.tab_orders = QWidget()
        self.init_orders_tab()
        self.tabs.addTab(self.tab_orders, "Purchase Orders")

        # Tab 4: Sales & Refunds
        self.tab_sales = QWidget()
        self.init_sales_tab()
        self.tabs.addTab(self.tab_sales, "Sales & Refunds")

        # Tab 5: Stock Log
        self.tab_movements = QWidget()
        self.init_movements_tab()
        self.tabs.addTab(self.tab_movements, "Stock Log")

        self.load_inventory()

    # ------------------------------------------------------------------ #
    # INVENTORY TAB                                                       #
    # ------------------------------------------------------------------ #
    def init_inventory_tab(self):
        layout = QVBoxLayout(self.tab_inventory)

        self.lbl_summary = QLabel("Products: 0   |   Stock Value (Incl. VAT): $0.00   |   Low Stock Alerts: 0")
        self.lbl_summary.setObjectName("lblSummary")
        layout.addWidget(self.lbl_summary)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by SKU, Name or Category...")
        self.search_input.textChanged.connect(self.filter_inventory)

        btn_add = QPushButton("+ Add Product")
        btn_add.clicked.connect(self.open_add_product_dialog)

        btn_adjust = QPushButton("Adjust Stock")
        btn_adjust.clicked.connect(self.open_adjust_stock_dialog)

        btn_sell = QPushButton("Sell Product")
        btn_sell.clicked.connect(self.sell_from_inventory)

        btn_delete = QPushButton("Delete Product")
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self.delete_selected_product)

        btn_import = QPushButton("Import Excel")
        btn_import.clicked.connect(self.import_excel)

        btn_export = QPushButton("Export Excel")
        btn_export.clicked.connect(self.export_excel)

        toolbar.addWidget(self.search_input, 1)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_adjust)
        toolbar.addWidget(btn_sell)
        toolbar.addWidget(btn_delete)
        toolbar.addWidget(btn_import)
        toolbar.addWidget(btn_export)
        layout.addLayout(toolbar)

        self.table_inv = QTableWidget()
        self.table_inv.setColumnCount(10)
        self.table_inv.setHorizontalHeaderLabels([
            "ID", "SKU", "Product Name", "Category", "Stock", "Min Limit",
            "Cost Excl. Tax ($)", "Sell Excl. Tax ($)", "Sell Incl. VAT ($)", "Location",
        ])
        self.table_inv.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_inv.itemChanged.connect(self.on_cell_edited)
        layout.addWidget(self.table_inv)

    def load_inventory(self):
        self.table_inv.blockSignals(True)
        self.table_inv.setRowCount(0)
        db = SessionLocal()
        try:
            products = db.query(Product).order_by(Product.sku).all()
            for p in products:
                row = self.table_inv.rowCount()
                self.table_inv.insertRow(row)

                selling_ht = p.selling_price_excl_tax or 0.0
                vat_rate = p.vat_rate or 20.0
                ttc_price = selling_ht * (1 + vat_rate / 100.0)

                items = [
                    QTableWidgetItem(str(p.id)),
                    QTableWidgetItem(p.sku),
                    QTableWidgetItem(p.name),
                    QTableWidgetItem(p.category or ""),
                    QTableWidgetItem(str(p.quantity or 0)),
                    QTableWidgetItem(str(p.min_threshold or 0)),
                    QTableWidgetItem(f"{p.purchase_price_excl_tax or 0.0:.2f}"),
                    QTableWidgetItem(f"{selling_ht:.2f}"),
                    QTableWidgetItem(f"{ttc_price:.2f}"),
                    QTableWidgetItem(p.location or ""),
                ]

                items[0].setFlags(items[0].flags() & ~Qt.ItemIsEditable)
                items[8].setFlags(items[8].flags() & ~Qt.ItemIsEditable)

                if (p.quantity or 0) <= (p.min_threshold or 0):
                    for item in items:
                        item.setBackground(QColor("#fee2e2"))
                        item.setForeground(QColor("#991b1b"))

                for col, item in enumerate(items):
                    self.table_inv.setItem(row, col, item)
        finally:
            db.close()
        self.table_inv.blockSignals(False)

        self.refresh_summary()
        if self.search_input.text():
            self.filter_inventory(self.search_input.text())

    def refresh_summary(self):
        summary = StockService.get_inventory_summary()
        low_html = (
            f'<span style="color:#dc2626; font-weight:bold;">Low Stock Alerts: {summary["low_stock"]}</span>'
            if summary["low_stock"] else "Low Stock Alerts: 0"
        )
        self.lbl_summary.setText(
            f"Products: {summary['count']}   |   Stock Value (Incl. VAT): "
            f"${summary['total_value_ttc']:,.2f}   |   {low_html}"
        )

    def on_cell_edited(self, item):
        row = item.row()
        if row < 0 or item.column() in (0, 8):
            return

        def cell_text(col):
            cell = self.table_inv.item(row, col)
            return cell.text().strip() if cell else ""

        data = {
            "product_id": cell_text(0),
            "sku": cell_text(1),
            "name": cell_text(2),
            "category": cell_text(3),
            "quantity": cell_text(4),
            "min_threshold": cell_text(5),
            "purchase_price_excl_tax": cell_text(6),
            "selling_price_excl_tax": cell_text(7),
            "location": cell_text(9),
        }
        success, msg = StockService.add_or_update_product(data)
        if not success:
            QMessageBox.warning(self, "Save Error", msg)
        self.load_inventory()

    def filter_inventory(self, text):
        text = text.lower()
        for row in range(self.table_inv.rowCount()):
            sku = self.table_inv.item(row, 1).text().lower()
            name = self.table_inv.item(row, 2).text().lower()
            cat = self.table_inv.item(row, 3).text().lower()
            match = text in sku or text in name or text in cat
            self.table_inv.setRowHidden(row, not match)

    def open_add_product_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Product (VAT Calculated)")
        layout = QFormLayout(dialog)

        sku = QLineEdit()
        name = QLineEdit()
        category = QLineEdit("General")
        qty = QLineEdit("0")
        min_stock = QLineEdit("5")
        p_price_ht = QLineEdit("0.0")
        s_price_ht = QLineEdit("0.0")
        vat = QLineEdit("20")
        s_price_ttc = QLineEdit("0.00")
        s_price_ttc.setReadOnly(True)
        loc = QLineEdit("A-01")

        def calculate_ttc():
            try:
                ht = float(s_price_ht.text() or 0)
                v = float(vat.text() or 0)
                s_price_ttc.setText(f"{ht * (1 + v / 100.0):.2f}")
            except ValueError:
                s_price_ttc.setText("0.00")

        s_price_ht.textChanged.connect(calculate_ttc)
        vat.textChanged.connect(calculate_ttc)

        layout.addRow("SKU Code:", sku)
        layout.addRow("Product Name:", name)
        layout.addRow("Category:", category)
        layout.addRow("Initial Stock:", qty)
        layout.addRow("Alert Level:", min_stock)
        layout.addRow("Cost Price Excl. Tax ($):", p_price_ht)
        layout.addRow("Selling Price Excl. Tax ($):", s_price_ht)
        layout.addRow("VAT Rate (%):", vat)
        layout.addRow("Selling Price Incl. VAT ($):", s_price_ttc)
        layout.addRow("Warehouse Location:", loc)

        btn_save = QPushButton("Save Product")
        btn_save.clicked.connect(lambda: self.save_new_product(dialog, {
            "sku": sku.text(), "name": name.text(), "category": category.text(),
            "quantity": qty.text(), "min_threshold": min_stock.text(),
            "purchase_price_excl_tax": p_price_ht.text(),
            "selling_price_excl_tax": s_price_ht.text(),
            "vat_rate": vat.text(),
            "location": loc.text(),
        }))
        layout.addRow(btn_save)
        dialog.exec()

    def save_new_product(self, dialog, data):
        success, msg = StockService.add_or_update_product(data)
        if success:
            dialog.accept()
            self.load_inventory()
            QMessageBox.information(self, "Saved", msg)
        else:
            QMessageBox.warning(self, "Save Error", msg)

    def open_adjust_stock_dialog(self):
        row = self.table_inv.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a product in the inventory table first.")
            return

        prod_id = int(self.table_inv.item(row, 0).text())
        name = self.table_inv.item(row, 2).text()
        current = self.table_inv.item(row, 4).text()

        dialog = QDialog(self)
        dialog.setWindowTitle("Adjust Stock")
        layout = QFormLayout(dialog)

        layout.addRow("Product:", QLabel(f"{name}  (current stock: {current})"))
        delta = QLineEdit()
        delta.setPlaceholderText("e.g. +10 to add, -5 to remove")
        reason = QLineEdit("Manual Adjustment")
        layout.addRow("Quantity Change:", delta)
        layout.addRow("Reason:", reason)

        btn = QPushButton("Apply Adjustment")
        btn.clicked.connect(lambda: self.apply_stock_adjustment(dialog, prod_id, delta.text(), reason.text()))
        layout.addRow(btn)
        dialog.exec()

    def apply_stock_adjustment(self, dialog, prod_id, delta, reason):
        success, msg = StockService.adjust_stock(prod_id, delta, reason)
        if success:
            dialog.accept()
            self.load_inventory()
            self.load_movements()
            QMessageBox.information(self, "Stock Adjusted", msg)
        else:
            QMessageBox.warning(self, "Adjustment Error", msg)

    def delete_selected_product(self):
        row = self.table_inv.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a product from the table to delete.")
            return

        prod_id = int(self.table_inv.item(row, 0).text())
        prod_name = self.table_inv.item(row, 2).text()

        confirm = QMessageBox.question(
            self, "Confirm Permanent Delete",
            f"Are you sure you want to PERMANENTLY delete product '{prod_name}' from the database?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.delete_product(prod_id)
            if success:
                QMessageBox.information(self, "Deleted", msg)
                self.load_inventory()
                self.load_movements()
            else:
                QMessageBox.warning(self, "Error", msg)

    def export_excel(self):
        default_path = f"inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Export Inventory", default_path, "Excel Files (*.xlsx)")
        if not path:
            return
        success, msg = StockService.export_inventory_to_excel(path)
        if success:
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.critical(self, "Export Error", msg)

    def import_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Inventory", "", "Excel Files (*.xlsx)")
        if not path:
            return
        success, msg = StockService.import_inventory_from_excel(path)
        if success:
            self.load_inventory()
            self.load_movements()
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.critical(self, "Import Error", msg)

    # ------------------------------------------------------------------ #
    # SUPPLIERS TAB                                                       #
    # ------------------------------------------------------------------ #
    def init_suppliers_tab(self):
        layout = QVBoxLayout(self.tab_suppliers)

        toolbar = QHBoxLayout()
        btn_add = QPushButton("+ Add Supplier")
        btn_add.clicked.connect(self.add_supplier_dialog)
        btn_edit = QPushButton("Edit Supplier")
        btn_edit.clicked.connect(self.edit_selected_supplier)
        btn_delete = QPushButton("Delete Supplier")
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self.delete_selected_supplier)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_delete)
        layout.addLayout(toolbar)

        self.table_sup = QTableWidget()
        self.table_sup.setColumnCount(6)
        self.table_sup.setHorizontalHeaderLabels(["ID", "Code", "Supplier Name", "Contact Person", "Email", "Phone"])
        self.table_sup.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_sup.cellDoubleClicked.connect(self.edit_selected_supplier)
        layout.addWidget(self.table_sup)
        self.load_suppliers()

    def load_suppliers(self):
        self.table_sup.setRowCount(0)
        db = SessionLocal()
        try:
            for sup in db.query(Supplier).order_by(Supplier.name).all():
                r = self.table_sup.rowCount()
                self.table_sup.insertRow(r)
                self.table_sup.setItem(r, 0, QTableWidgetItem(str(sup.id)))
                self.table_sup.setItem(r, 1, QTableWidgetItem(sup.code))
                self.table_sup.setItem(r, 2, QTableWidgetItem(sup.name))
                self.table_sup.setItem(r, 3, QTableWidgetItem(sup.contact_person or ""))
                self.table_sup.setItem(r, 4, QTableWidgetItem(sup.email or ""))
                self.table_sup.setItem(r, 5, QTableWidgetItem(sup.phone or ""))
        finally:
            db.close()

    def add_supplier_dialog(self):
        self.supplier_form(None)

    def edit_selected_supplier(self, row=None, col=0):
        row = self.table_sup.currentRow() if row is None else row
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a supplier to edit.")
            return
        sup_id = int(self.table_sup.item(row, 0).text())
        db = SessionLocal()
        try:
            sup = db.query(Supplier).filter(Supplier.id == sup_id).first()
        finally:
            db.close()
        if sup:
            self.supplier_form(sup)

    def supplier_form(self, supplier):
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Supplier" if supplier else "New Supplier")
        layout = QFormLayout(dialog)

        code = QLineEdit(supplier.code if supplier else "")
        name = QLineEdit(supplier.name if supplier else "")
        contact = QLineEdit(supplier.contact_person or "" if supplier else "")
        email = QLineEdit(supplier.email or "" if supplier else "")
        phone = QLineEdit(supplier.phone or "" if supplier else "")

        layout.addRow("Supplier Code:", code)
        layout.addRow("Company Name:", name)
        layout.addRow("Contact Person:", contact)
        layout.addRow("Email Address:", email)
        layout.addRow("Phone:", phone)

        btn = QPushButton("Save Supplier")
        btn.clicked.connect(lambda: self.save_supplier(
            dialog, supplier.id if supplier else None,
            code.text(), name.text(), contact.text(), email.text(), phone.text(),
        ))
        layout.addRow(btn)
        dialog.exec()

    def save_supplier(self, dialog, supplier_id, code, name, contact, email, phone):
        if supplier_id:
            success, msg = StockService.update_supplier(supplier_id, code, name, contact, email, phone)
        else:
            success, msg = StockService.add_supplier(code, name, contact, email, phone)
        if success:
            dialog.accept()
            self.load_suppliers()
            QMessageBox.information(self, "Saved", msg)
        else:
            QMessageBox.warning(self, "Save Error", msg)

    def delete_selected_supplier(self):
        row = self.table_sup.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a supplier to delete.")
            return

        sup_id = int(self.table_sup.item(row, 0).text())
        sup_name = self.table_sup.item(row, 2).text()

        confirm = QMessageBox.question(
            self, "Confirm Permanent Delete",
            f"Are you sure you want to PERMANENTLY delete supplier '{sup_name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.delete_supplier(sup_id)
            if success:
                QMessageBox.information(self, "Deleted", msg)
                self.load_suppliers()
            else:
                QMessageBox.warning(self, "Error", msg)

    # ------------------------------------------------------------------ #
    # PURCHASE ORDERS TAB                                                 #
    # ------------------------------------------------------------------ #
    def init_orders_tab(self):
        layout = QVBoxLayout(self.tab_orders)

        toolbar = QHBoxLayout()
        btn_add_order = QPushButton("+ Create Order")
        btn_add_order.clicked.connect(self.create_order_dialog)

        btn_rec = QPushButton("Receive Order")
        btn_rec.clicked.connect(self.receive_selected_order)

        btn_cancel = QPushButton("Cancel / Return")
        btn_cancel.clicked.connect(self.cancel_selected_order)

        btn_delete = QPushButton("Delete Order Permanently")
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self.delete_order_permanently)

        toolbar.addWidget(btn_add_order)
        toolbar.addWidget(btn_rec)
        toolbar.addWidget(btn_cancel)
        toolbar.addWidget(btn_delete)
        layout.addLayout(toolbar)

        self.table_orders = QTableWidget()
        self.table_orders.setColumnCount(7)
        self.table_orders.setHorizontalHeaderLabels([
            "Order ID", "Reference", "Supplier", "Status",
            "Total Excl. Tax ($)", "Total Incl. VAT ($)", "Date",
        ])
        self.table_orders.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_orders.cellDoubleClicked.connect(self.show_order_details)
        layout.addWidget(self.table_orders)

        self.lbl_orders_total = QLabel("Total Orders (Incl. VAT): $0.00")
        self.lbl_orders_total.setObjectName("lblSummary")
        layout.addWidget(self.lbl_orders_total)
        self.load_orders()

    def load_orders(self):
        self.table_orders.setRowCount(0)
        total_ttc = 0.0
        db = SessionLocal()
        try:
            orders = db.query(PurchaseOrder).order_by(PurchaseOrder.order_date.desc()).all()
            for o in orders:
                r = self.table_orders.rowCount()
                self.table_orders.insertRow(r)

                status_val = o.status.value if o.status else "Unknown"
                total_ht = o.total_excl_tax or 0.0
                vat_rate = o.vat_rate or 20.0
                ttc = total_ht * (1 + vat_rate / 100.0)
                total_ttc += ttc

                row_items = [
                    QTableWidgetItem(str(o.id)),
                    QTableWidgetItem(o.reference),
                    QTableWidgetItem(o.supplier.name if o.supplier else "N/A"),
                    QTableWidgetItem(status_val),
                    QTableWidgetItem(f"{total_ht:.2f}"),
                    QTableWidgetItem(f"{ttc:.2f}"),
                    QTableWidgetItem(o.order_date.strftime("%Y-%m-%d %H:%M") if o.order_date else ""),
                ]

                status_key = o.status.name if o.status else ""
                bg = {
                    OrderStatus.RECEIVED.name: "#e8f5e9",
                    OrderStatus.ORDERED.name: "#fff8e1",
                    OrderStatus.CANCELLED.name: "#fdecea",
                }.get(status_key)
                fg = {
                    OrderStatus.RECEIVED.name: "#1e7e34",
                    OrderStatus.ORDERED.name: "#9a6b00",
                    OrderStatus.CANCELLED.name: "#c62828",
                }.get(status_key)
                if bg and fg:
                    for item in row_items:
                        item.setBackground(QColor(bg))
                        item.setForeground(QColor(fg))

                for col, item in enumerate(row_items):
                    self.table_orders.setItem(r, col, item)
        finally:
            db.close()
        self.lbl_orders_total.setText(f"Total Orders (Incl. VAT): ${total_ttc:,.2f}")

    def create_order_dialog(self):
        db = SessionLocal()
        try:
            suppliers = db.query(Supplier).order_by(Supplier.name).all()
            products = db.query(Product).order_by(Product.sku).all()
        finally:
            db.close()

        if not suppliers:
            QMessageBox.warning(self, "Warning", "Please register at least one supplier first.")
            return
        if not products:
            QMessageBox.warning(self, "Warning", "Please register at least one product first.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Create Purchase Order")
        layout = QFormLayout(dialog)

        # Added seconds (%S) to avoid duplicate reference collisions
        unique_ref = f"PO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ref_input = QLineEdit(unique_ref)

        sup_combo = QComboBox()
        for s in suppliers:
            sup_combo.addItem(f"{s.code} - {s.name}", s.id)

        prod_combo = QComboBox()
        for p in products:
            prod_combo.addItem(f"{p.sku} - {p.name} ({p.quantity or 0} in stock)", p.id)

        qty_input = QLineEdit("10")

        layout.addRow("Order Reference:", ref_input)
        layout.addRow("Supplier:", sup_combo)
        layout.addRow("Product:", prod_combo)
        layout.addRow("Quantity:", qty_input)

        btn = QPushButton("Submit Order")
        btn.clicked.connect(lambda: self.save_new_order(
            dialog, ref_input.text(), sup_combo.currentData(),
            prod_combo.currentData(), qty_input.text(),
        ))
        layout.addRow(btn)
        dialog.exec()

    def save_new_order(self, dialog, ref, sup_id, prod_id, qty_text):
        try:
            qty = int(qty_text or "1")
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Quantity must be a whole number.")
            return
        if qty <= 0:
            QMessageBox.warning(self, "Input Error", "Quantity must be greater than zero.")
            return

        success, msg = StockService.create_order(
            ref, sup_id, [{"product_id": prod_id, "quantity": qty}]
        )
        if success:
            dialog.accept()
            self.load_orders()
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.warning(self, "Order Error", msg)

    def receive_selected_order(self):
        row = self.table_orders.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select an order to receive.")
            return
        order_id = int(self.table_orders.item(row, 0).text())
        success, msg = StockService.receive_order(order_id)
        if success:
            QMessageBox.information(self, "Success", msg)
            self.load_orders()
            self.load_inventory()
            self.load_movements()
        else:
            QMessageBox.warning(self, "Error", msg)

    def cancel_selected_order(self):
        row = self.table_orders.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select an order to cancel.")
            return

        order_id = int(self.table_orders.item(row, 0).text())

        reply = QMessageBox.question(
            self, "Confirm Cancel/Return",
            "Are you sure you want to cancel/return this order?\n"
            "If it was already received, stock will be automatically deducted.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            success, msg = StockService.cancel_or_return_order(order_id)
            if success:
                QMessageBox.information(self, "Cancelled", msg)
                self.load_orders()
                self.load_inventory()
                self.load_movements()
            else:
                QMessageBox.warning(self, "Error", msg)

    def delete_order_permanently(self):
        row = self.table_orders.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select an order to permanently delete.")
            return

        order_id = int(self.table_orders.item(row, 0).text())
        order_ref = self.table_orders.item(row, 1).text()

        confirm = QMessageBox.question(
            self, "PERMANENT DELETE",
            f"Are you sure you want to PERMANENTLY DELETE order '{order_ref}' from the database?\n\n"
            "This action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.delete_order_permanently(order_id, revert_stock=True)
            if success:
                QMessageBox.information(self, "Deleted", msg)
                self.load_orders()
                self.load_inventory()
                self.load_movements()
            else:
                QMessageBox.warning(self, "Error", msg)

    def show_order_details(self, row, col=0):
        if row < 0:
            return
        order_id = int(self.table_orders.item(row, 0).text())
        data = StockService.get_order_details(order_id)
        if not data:
            QMessageBox.warning(self, "Order", "Order not found.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Order {data['reference']} - Details")
        dialog.resize(620, 380)
        layout = QVBoxLayout(dialog)

        status_val = data["status"].value if data["status"] else "Unknown"
        total_ttc = data["total_excl_tax"] * (1 + (data["vat_rate"] or 20.0) / 100.0)
        header = QLabel(
            f"Status: {status_val}    |    Total Excl. Tax: ${data['total_excl_tax']:.2f}    "
            f"|    Total Incl. VAT: ${total_ttc:.2f}"
        )
        layout.addWidget(header)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Product", "Quantity", "Unit Cost ($)", "Line Total ($)"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for item_data in data["items"]:
            r = table.rowCount()
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(f"{item_data['sku']} - {item_data['name']}"))
            table.setItem(r, 1, QTableWidgetItem(str(item_data["quantity"])))
            table.setItem(r, 2, QTableWidgetItem(f"{item_data['unit_cost']:.2f}"))
            table.setItem(r, 3, QTableWidgetItem(f"{item_data['line_total']:.2f}"))
        if not data["items"]:
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem("This order has no items."))
        layout.addWidget(table)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.exec()

    # ------------------------------------------------------------------ #
    # SALES & REFUNDS TAB                                                #
    # ------------------------------------------------------------------ #
    def init_sales_tab(self):
        layout = QVBoxLayout(self.tab_sales)

        toolbar = QHBoxLayout()
        btn_new_sale = QPushButton("+ New Sale")
        btn_new_sale.clicked.connect(self.create_sale_dialog)

        btn_refund = QPushButton("Return / Refund (14 days)")
        btn_refund.clicked.connect(self.refund_selected_sale)

        btn_delete = QPushButton("Delete Sale Permanently")
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self.delete_sale_permanently)

        toolbar.addWidget(btn_new_sale)
        toolbar.addWidget(btn_refund)
        toolbar.addWidget(btn_delete)
        layout.addLayout(toolbar)

        self.table_sales = QTableWidget()
        self.table_sales.setColumnCount(9)
        self.table_sales.setHorizontalHeaderLabels([
            "Sale ID", "Reference", "Product", "Qty", "Unit Price Excl. Tax ($)",
            "Total Incl. VAT ($)", "Date", "Status", "Refund Date",
        ])
        self.table_sales.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_sales)

        self.lbl_sales_total = QLabel("Total Sales (Incl. VAT): $0.00")
        self.lbl_sales_total.setObjectName("lblSummary")
        layout.addWidget(self.lbl_sales_total)

        self.load_sales()

    def load_sales(self):
        self.table_sales.setRowCount(0)
        db = SessionLocal()
        try:
            sales = db.query(Sale).order_by(Sale.sale_date.desc()).all()
            for s in sales:
                r = self.table_sales.rowCount()
                self.table_sales.insertRow(r)

                total_ttc = (s.total_excl_tax or 0.0) * (1 + (s.vat_rate or 20.0) / 100.0)
                status_val = s.status.value if s.status else "Unknown"

                row_items = [
                    QTableWidgetItem(str(s.id)),
                    QTableWidgetItem(s.reference),
                    QTableWidgetItem(
                        f"{s.product.sku if s.product else 'N/A'} - "
                        f"{s.product.name if s.product else 'Unknown product'}"
                    ),
                    QTableWidgetItem(str(s.quantity)),
                    QTableWidgetItem(f"{s.unit_price_excl_tax or 0.0:.2f}"),
                    QTableWidgetItem(f"{total_ttc:.2f}"),
                    QTableWidgetItem(s.sale_date.strftime("%Y-%m-%d %H:%M") if s.sale_date else ""),
                    QTableWidgetItem(status_val),
                    QTableWidgetItem(s.refund_date.strftime("%Y-%m-%d %H:%M") if s.refund_date else ""),
                ]

                status_key = s.status.name if s.status else ""
                bg = {
                    SaleStatus.SOLD.name: "#e8f5e9",
                    SaleStatus.REFUNDED.name: "#f3f4f6",
                }.get(status_key)
                fg = {
                    SaleStatus.SOLD.name: "#1e7e34",
                    SaleStatus.REFUNDED.name: "#6b7280",
                }.get(status_key)
                if bg and fg:
                    for item in row_items:
                        item.setBackground(QColor(bg))
                        item.setForeground(QColor(fg))

                for col, item in enumerate(row_items):
                    self.table_sales.setItem(r, col, item)
        finally:
            db.close()
        self.refresh_sales_total()

    def refresh_sales_total(self):
        summary = StockService.get_sales_summary()
        net = summary["total_sold_ttc"] - summary["total_refunded_ttc"]
        self.lbl_sales_total.setText(
            f"Total Sales (Incl. VAT): ${summary['total_sold_ttc']:,.2f}    |    "
            f"Total Refunded (Incl. VAT): ${summary['total_refunded_ttc']:,.2f}    |    "
            f"Net: ${net:,.2f}    |    "
            f"Sales: {summary['sold_count']}    Refunds: {summary['refunded_count']}"
        )

    def sell_from_inventory(self):
        row = self.table_inv.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a product in the inventory table first.")
            return
        self.create_sale_dialog(preselected_product_id=int(self.table_inv.item(row, 0).text()))

    def create_sale_dialog(self, preselected_product_id=None):
        db = SessionLocal()
        try:
            products = db.query(Product).order_by(Product.sku).all()
        finally:
            db.close()

        if not products:
            QMessageBox.warning(self, "Warning", "Please register at least one product first.")
            return

        price_map = {p.id: (p.selling_price_excl_tax or 0.0) for p in products}

        dialog = QDialog(self)
        dialog.setWindowTitle("New Sale")
        layout = QFormLayout(dialog)

        unique_ref = f"SA-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ref_input = QLineEdit(unique_ref)

        prod_combo = QComboBox()
        for p in products:
            prod_combo.addItem(f"{p.sku} - {p.name} ({p.quantity or 0} in stock)", p.id)

        qty_input = QLineEdit("1")
        unit_price = QLineEdit()
        vat = QLineEdit("20")
        lbl_total = QLabel("Total Incl. VAT: $0.00")
        lbl_total.setStyleSheet("font-weight: bold; color: #107c41;")

        def update_total():
            try:
                q = int(qty_input.text() or "0")
                p = float(unit_price.text() or "0")
                v = float(vat.text() or "0")
                lbl_total.setText(f"Total Incl. VAT: ${p * q * (1 + v / 100.0):,.2f}")
            except ValueError:
                lbl_total.setText("Total Incl. VAT: $0.00")

        def refresh_price():
            pid = prod_combo.currentData()
            unit_price.setText(f"{price_map.get(pid, 0.0):.2f}")
            update_total()

        prod_combo.currentIndexChanged.connect(refresh_price)
        qty_input.textChanged.connect(update_total)
        unit_price.textChanged.connect(update_total)
        vat.textChanged.connect(update_total)
        refresh_price()

        if preselected_product_id is not None:
            idx = prod_combo.findData(preselected_product_id)
            if idx >= 0:
                prod_combo.setCurrentIndex(idx)
                refresh_price()

        layout.addRow("Sale Reference:", ref_input)
        layout.addRow("Product:", prod_combo)
        layout.addRow("Quantity:", qty_input)
        layout.addRow("Unit Price Excl. Tax ($):", unit_price)
        layout.addRow("VAT Rate (%):", vat)
        layout.addRow(lbl_total)

        btn = QPushButton("Record Sale")
        btn.clicked.connect(lambda: self.save_new_sale(
            dialog, ref_input.text(), prod_combo.currentData(),
            qty_input.text(), unit_price.text(), vat.text(),
        ))
        layout.addRow(btn)
        dialog.exec()

    def save_new_sale(self, dialog, ref, prod_id, qty_text, price_text, vat_text):
        success, msg = StockService.create_sale(ref, prod_id, qty_text, price_text, vat_text)
        if success:
            dialog.accept()
            self.load_sales()
            self.load_inventory()
            self.load_movements()
            QMessageBox.information(self, "Sale Recorded", msg)
        else:
            QMessageBox.warning(self, "Sale Error", msg)

    def refund_selected_sale(self):
        row = self.table_sales.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a sale to refund.")
            return

        sale_id = int(self.table_sales.item(row, 0).text())
        sale_ref = self.table_sales.item(row, 1).text()

        confirm = QMessageBox.question(
            self, "Confirm Refund",
            f"Return sale '{sale_ref}' and refund the customer?\n\n"
            "(Only allowed within 14 days of the sale. Stock will be restored.)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.refund_sale(sale_id)
            if success:
                QMessageBox.information(self, "Refunded", msg)
                self.load_sales()
                self.load_inventory()
                self.load_movements()
            else:
                QMessageBox.warning(self, "Refund Error", msg)

    def delete_sale_permanently(self):
        row = self.table_sales.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a sale to permanently delete.")
            return

        sale_id = int(self.table_sales.item(row, 0).text())
        sale_ref = self.table_sales.item(row, 1).text()

        confirm = QMessageBox.question(
            self, "PERMANENT DELETE",
            f"Are you sure you want to PERMANENTLY DELETE sale '{sale_ref}'?\n\n"
            "This action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.delete_sale_permanently(sale_id, revert_stock=True)
            if success:
                QMessageBox.information(self, "Deleted", msg)
                self.load_sales()
                self.load_inventory()
                self.load_movements()
            else:
                QMessageBox.warning(self, "Error", msg)

    # ------------------------------------------------------------------ #
    # STOCK LOG TAB                                                       #
    # ------------------------------------------------------------------ #
    def init_movements_tab(self):
        layout = QVBoxLayout(self.tab_movements)

        self.search_mov = QLineEdit()
        self.search_mov.setPlaceholderText("Filter by SKU, movement type or reference...")
        self.search_mov.textChanged.connect(self.filter_movements)
        layout.addWidget(self.search_mov)

        self.table_mov = QTableWidget()
        self.table_mov.setColumnCount(5)
        self.table_mov.setHorizontalHeaderLabels([
            "Date/Time", "Product (SKU)", "Movement Type", "Quantity", "Reference / Reason",
        ])
        self.table_mov.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_mov)
        self.load_movements()

    def load_movements(self):
        self.table_mov.setRowCount(0)
        db = SessionLocal()
        try:
            movements = db.query(StockMovement).order_by(StockMovement.created_at.desc()).all()
            for m in movements:
                r = self.table_mov.rowCount()
                self.table_mov.insertRow(r)
                self.table_mov.setItem(r, 0, QTableWidgetItem(
                    m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else ""
                ))
                self.table_mov.setItem(r, 1, QTableWidgetItem(m.product.sku if m.product else "N/A"))
                self.table_mov.setItem(r, 2, QTableWidgetItem(m.type.value if m.type else ""))
                self.table_mov.setItem(r, 3, QTableWidgetItem(str(m.quantity)))
                self.table_mov.setItem(r, 4, QTableWidgetItem(m.reference or ""))
        finally:
            db.close()

    def filter_movements(self, text):
        text = text.lower()
        for row in range(self.table_mov.rowCount()):
            sku = (self.table_mov.item(row, 1).text() or "").lower()
            mtype = (self.table_mov.item(row, 2).text() or "").lower()
            ref = (self.table_mov.item(row, 4).text() or "").lower()
            self.table_mov.setRowHidden(row, not (text in sku or text in mtype or text in ref))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
