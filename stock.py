import sys
from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from DBase import (
    init_db, backup_database, SessionLocal, Product, Supplier, Customer, PurchaseOrder,
    StockMovement, MovementType, OrderStatus, Sale, SaleStatus,
)
from services import StockService
from i18n import (
    tr, set_language, get_language, load_language, save_language,
    SUPPORTED_LANGUAGES,
)

# Excel White Theme
# Explicit colors everywhere so the UI stays readable even on dark desktop
# themes (e.g. Kali Linux), which would otherwise inject white foreground text.
STYLE_SHEET = """
QWidget {
    background-color: #f8f9fa;
    color: #111827;
}
QMainWindow {
    background-color: #f8f9fa;
}
QDialog {
    background-color: #f8f9fa;
}
QLabel {
    color: #111827;
    background: transparent;
}
QToolTip {
    background-color: #1f2937;
    color: #ffffff;
    border: 1px solid #111827;
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
QLineEdit, QComboBox, QDateEdit {
    background-color: #ffffff;
    color: #1f2937;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 6px;
    selection-background-color: #107c41;
    selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 1px solid #107c41;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #1f2937;
    border: 1px solid #d1d5db;
    selection-background-color: #107c41;
    selection-color: #ffffff;
}
QTableCornerButton::section {
    background-color: #f3f4f6;
    border: 1px solid #d1d5db;
}
QLabel#lblSummary {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 8px 12px;
    font-weight: bold;
    font-size: 13px;
}
QLabel#lblCard {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 10px 12px;
}
QLabel#lblPreview {
    background-color: #eef7f1;
    border: 1px solid #107c41;
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 12px;
}
QCheckBox {
    color: #111827;
    spacing: 6px;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        set_language(load_language())
        self.setWindowTitle(tr("app.title"))
        self.resize(1300, 760)
        self.setStyleSheet(STYLE_SHEET)

        init_db()
        self._last_backup_str = None
        self.init_ui()
        try:
            self.perform_backup(silent=True)
        except Exception:
            pass

    def perform_backup(self, silent=False):
        try:
            result = backup_database()
            if result is None:
                if not silent:
                    QMessageBox.warning(
                        self, tr("msg.error"), tr("bak.no_file")
                    )
                return
            self._last_backup_str = result["created"].strftime("%Y-%m-%d %H:%M:%S")
            self.update_backup_label()
            if not silent:
                QMessageBox.information(
                    self, tr("bak.done"),
                    tr("bak.done_body", path=result["path"], kept=result["kept"]),
                )
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, tr("msg.error"), tr("bak.error", error=e))

    def update_backup_label(self):
        if getattr(self, "lbl_backup", None) is None:
            return
        if self._last_backup_str:
            self.lbl_backup.setText(tr("bak.last", time=self._last_backup_str))
        else:
            self.lbl_backup.setText(tr("bak.never"))

    def closeEvent(self, event):
        try:
            self.perform_backup(silent=True)
        except Exception:
            pass
        event.accept()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        header = QHBoxLayout()
        header.addStretch(1)
        lbl_lang = QLabel(tr("app.language"))
        header.addWidget(lbl_lang)
        self.lang_combo = QComboBox()
        for code, label in SUPPORTED_LANGUAGES.items():
            self.lang_combo.addItem(label, code)
        lang_idx = self.lang_combo.findData(get_language())
        if lang_idx >= 0:
            self.lang_combo.setCurrentIndex(lang_idx)
        self.lang_combo.currentIndexChanged.connect(self.on_language_changed)
        header.addWidget(self.lang_combo)

        header.addSpacing(12)
        self.btn_backup = QPushButton(tr("bak.btn"))
        self.btn_backup.clicked.connect(lambda: self.perform_backup(silent=False))
        header.addWidget(self.btn_backup)
        self.lbl_backup = QLabel("")
        self.lbl_backup.setObjectName("lblSummary")
        self.update_backup_label()
        header.addWidget(self.lbl_backup)

        main_layout.addLayout(header)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab 1: Inventory
        self.tab_inventory = QWidget()
        self.init_inventory_tab()
        self.tabs.addTab(self.tab_inventory, tr("tab.inventory"))

        # Tab 2: Suppliers
        self.tab_suppliers = QWidget()
        self.init_suppliers_tab()
        self.tabs.addTab(self.tab_suppliers, tr("tab.suppliers"))

        # Tab 3: Customers
        self.tab_customers = QWidget()
        self.init_customers_tab()
        self.tabs.addTab(self.tab_customers, tr("tab.customers"))

        # Tab 4: Purchase Orders
        self.tab_orders = QWidget()
        self.init_orders_tab()
        self.tabs.addTab(self.tab_orders, tr("tab.orders"))

        # Tab 5: Sales & Refunds
        self.tab_sales = QWidget()
        self.init_sales_tab()
        self.tabs.addTab(self.tab_sales, tr("tab.sales"))

        # Tab 6: Stock Log
        self.tab_movements = QWidget()
        self.init_movements_tab()
        self.tabs.addTab(self.tab_movements, tr("tab.movements"))

        # Tab 7: Finance
        self.tab_finance = QWidget()
        self.init_finance_tab()
        self.tabs.addTab(self.tab_finance, tr("tab.finance"))

        self.load_inventory()

    def on_language_changed(self):
        lang = self.lang_combo.currentData()
        if lang and lang != get_language():
            set_language(lang)
            save_language(lang)
            self.setWindowTitle(tr("app.title"))
            current = self.tabs.currentIndex()
            self.init_ui()
            self.tabs.setCurrentIndex(current)

    # ------------------------------------------------------------------ #
    # Status helpers (translate enum -> display text)                     #
    # ------------------------------------------------------------------ #
    def _order_status_text(self, status):
        if status is None:
            return tr("status.unknown")
        return tr(f"status.{status.name.lower()}")

    def _sale_status_text(self, status):
        if status is None:
            return tr("status.unknown")
        return tr(f"status.{status.name.lower()}")

    # ------------------------------------------------------------------ #
    # INVENTORY TAB                                                       #
    # ------------------------------------------------------------------ #
    def init_inventory_tab(self):
        layout = QVBoxLayout(self.tab_inventory)

        self.lbl_summary = QLabel(
            tr("inv.summary", count=0, value=0.0, low_html=f'{tr("msg.low_stock_alerts")}: 0')
        )
        self.lbl_summary.setObjectName("lblSummary")
        layout.addWidget(self.lbl_summary)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("inv.search_placeholder"))
        self.search_input.textChanged.connect(self.filter_inventory)

        btn_add = QPushButton(tr("inv.btn_add"))
        btn_add.clicked.connect(self.open_add_product_dialog)

        btn_adjust = QPushButton(tr("inv.btn_adjust"))
        btn_adjust.clicked.connect(self.open_adjust_stock_dialog)

        btn_sell = QPushButton(tr("inv.btn_sell"))
        btn_sell.clicked.connect(self.sell_from_inventory)

        btn_delete = QPushButton(tr("inv.btn_delete"))
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self.delete_selected_product)

        btn_import = QPushButton(tr("inv.btn_import"))
        btn_import.clicked.connect(self.import_excel)

        btn_export = QPushButton(tr("inv.btn_export"))
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
            tr("inv.col_id"), tr("inv.col_sku"), tr("inv.col_name"),
            tr("inv.col_category"), tr("inv.col_stock"), tr("inv.col_min_limit"),
            tr("inv.col_cost_ht"), tr("inv.col_sell_ht"), tr("inv.col_sell_ttc"),
            tr("inv.col_location"),
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
        if summary["low_stock"]:
            low_html = (
                f'<span style="color:#dc2626; font-weight:bold;">'
                f'{tr("msg.low_stock_alerts")}: {summary["low_stock"]}'
                f"</span>"
            )
        else:
            low_html = f'{tr("msg.low_stock_alerts")}: 0'
        self.lbl_summary.setText(
            tr(
                "inv.summary",
                count=summary["count"],
                value=summary["total_value_ttc"],
                low_html=low_html,
            )
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
            QMessageBox.warning(self, tr("msg.save_error"), msg)
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
        dialog.setWindowTitle(tr("dlg.add_product"))
        layout = QFormLayout(dialog)

        sku = QLineEdit()
        name = QLineEdit()
        category = QLineEdit(tr("dlg.default_category"))
        qty = QLineEdit("0")
        min_stock = QLineEdit("5")
        p_price_ht = QLineEdit("0.0")
        s_price_ht = QLineEdit("0.0")
        vat = QLineEdit("20")
        s_price_ttc = QLineEdit("0.00")
        s_price_ttc.setReadOnly(True)
        loc = QLineEdit(tr("dlg.default_location"))

        preview = QLabel(tr("dlg.preview_empty"))
        preview.setObjectName("lblPreview")

        def calculate_ttc():
            try:
                ht = float(s_price_ht.text() or 0)
                v = float(vat.text() or 0)
                s_price_ttc.setText(f"{ht * (1 + v / 100.0):.2f}")
            except ValueError:
                s_price_ttc.setText("0.00")
            refresh_preview()

        def refresh_preview():
            info = {
                "name": name.text().strip(),
                "sku": sku.text().strip(),
                "category": category.text().strip() or tr("dlg.default_category"),
                "cost": 0.0,
                "price": 0.0,
                "ttc": 0.0,
                "qty": 0,
                "value": 0.0,
                "revenue": 0.0,
                "margin": 0.0,
            }
            try:
                info["cost"] = float(p_price_ht.text() or 0)
                info["price"] = float(s_price_ht.text() or 0)
                info["ttc"] = info["price"] * (1 + float(vat.text() or 0) / 100.0)
                info["qty"] = int(qty.text() or 0)
                info["value"] = info["cost"] * info["qty"]
                info["revenue"] = info["ttc"] * info["qty"]
                info["margin"] = (info["price"] - info["cost"]) / info["price"] * 100.0 if info["price"] else 0.0
            except (TypeError, ValueError):
                pass
            if not info["name"] and not info["sku"]:
                preview.setText(tr("dlg.preview_empty"))
                return
            preview.setText(tr(
                "dlg.preview",
                name=info["name"] or tr("dlg.preview_unnamed"),
                sku=info["sku"] or tr("dlg.preview_nosku"),
                category=info["category"],
                cost=info["cost"],
                price=info["price"],
                ttc=info["ttc"],
                qty=info["qty"],
                value=info["value"],
                revenue=info["revenue"],
                margin=info["margin"],
            ))

        for field in (sku, name, category, qty, p_price_ht, s_price_ht, vat, loc):
            field.textChanged.connect(refresh_preview)
        s_price_ht.textChanged.connect(calculate_ttc)
        vat.textChanged.connect(calculate_ttc)
        refresh_preview()

        layout.addRow(tr("dlg.f_sku"), sku)
        layout.addRow(tr("dlg.f_name"), name)
        layout.addRow(tr("dlg.f_category"), category)
        layout.addRow(tr("dlg.f_qty"), qty)
        layout.addRow(tr("dlg.f_min"), min_stock)
        layout.addRow(tr("dlg.f_purchase_price"), p_price_ht)
        layout.addRow(tr("dlg.f_sell_price"), s_price_ht)
        layout.addRow(tr("dlg.f_vat"), vat)
        layout.addRow(tr("dlg.f_sell_ttc"), s_price_ttc)
        layout.addRow(tr("dlg.f_location"), loc)

        layout.addRow(preview)

        btn_save = QPushButton(tr("dlg.btn_save"))
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
            QMessageBox.information(self, tr("msg.saved"), msg)
        else:
            QMessageBox.warning(self, tr("msg.save_error"), msg)

    def open_adjust_stock_dialog(self):
        row = self.table_inv.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_product_first")
            )
            return

        prod_id = int(self.table_inv.item(row, 0).text())
        name = self.table_inv.item(row, 2).text()
        current = self.table_inv.item(row, 4).text()

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("adjust.title"))
        layout = QFormLayout(dialog)

        layout.addRow(
            tr("adjust.f_product"),
            QLabel(f"{name}  {tr('adjust.current', stock=current)}"),
        )
        new_qty = QLineEdit(current)
        new_qty.setPlaceholderText(tr("adjust.placeholder"))
        reason = QLineEdit(tr("adjust.default_reason"))
        layout.addRow(tr("adjust.f_new_qty"), new_qty)
        layout.addRow(tr("adjust.f_reason"), reason)

        btn = QPushButton(tr("adjust.btn_apply"))
        btn.clicked.connect(lambda: self.apply_stock_adjustment(dialog, prod_id, new_qty.text(), reason.text()))
        layout.addRow(btn)
        dialog.exec()

    def apply_stock_adjustment(self, dialog, prod_id, new_qty, reason):
        success, msg = StockService.adjust_stock(prod_id, new_qty, reason)
        if success:
            dialog.accept()
            self.load_inventory()
            self.load_movements()
            QMessageBox.information(self, tr("msg.stock_adjusted"), msg)
        else:
            QMessageBox.warning(self, tr("msg.adjustment_error"), msg)

    def delete_selected_product(self):
        row = self.table_inv.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_product_delete")
            )
            return

        prod_id = int(self.table_inv.item(row, 0).text())
        prod_name = self.table_inv.item(row, 2).text()

        confirm = QMessageBox.question(
            self,
            tr("confirm.permanent_delete"),
            tr("confirm.delete_product", name=prod_name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.delete_product(prod_id)
            if success:
                QMessageBox.information(self, tr("msg.deleted"), msg)
                self.load_inventory()
                self.load_movements()
            else:
                QMessageBox.warning(self, tr("msg.error"), msg)

    def export_excel(self):
        default_path = f"inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("excel.export_title"), default_path, tr("excel.filter")
        )
        if not path:
            return
        success, msg = StockService.export_inventory_to_excel(path)
        if success:
            QMessageBox.information(self, tr("msg.success"), msg)
        else:
            QMessageBox.critical(self, tr("msg.export_error"), msg)

    def import_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("excel.import_title"), "", tr("excel.filter")
        )
        if not path:
            return
        success, msg = StockService.import_inventory_from_excel(path)
        if success:
            self.load_inventory()
            self.load_movements()
            QMessageBox.information(self, tr("msg.success"), msg)
        else:
            QMessageBox.critical(self, tr("msg.import_error"), msg)

    # ------------------------------------------------------------------ #
    # SUPPLIERS TAB                                                       #
    # ------------------------------------------------------------------ #
    def init_suppliers_tab(self):
        layout = QVBoxLayout(self.tab_suppliers)

        toolbar = QHBoxLayout()
        btn_add = QPushButton(tr("sup.btn_add"))
        btn_add.clicked.connect(self.add_supplier_dialog)
        btn_edit = QPushButton(tr("sup.btn_edit"))
        btn_edit.clicked.connect(self.edit_selected_supplier)
        btn_delete = QPushButton(tr("sup.btn_delete"))
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self.delete_selected_supplier)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_delete)
        layout.addLayout(toolbar)

        self.table_sup = QTableWidget()
        self.table_sup.setColumnCount(6)
        self.table_sup.setHorizontalHeaderLabels([
            tr("col.id"), tr("sup.col_code"), tr("sup.col_name"),
            tr("sup.col_contact"), tr("sup.col_email"), tr("sup.col_phone"),
        ])
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
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_supplier_edit")
            )
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
        dialog.setWindowTitle(tr("sup.dlg_edit") if supplier else tr("sup.dlg_new"))
        layout = QFormLayout(dialog)

        code = QLineEdit(supplier.code if supplier else "")
        name = QLineEdit(supplier.name if supplier else "")
        contact = QLineEdit(supplier.contact_person or "" if supplier else "")
        email = QLineEdit(supplier.email or "" if supplier else "")
        phone = QLineEdit(supplier.phone or "" if supplier else "")

        layout.addRow(tr("sup.f_code"), code)
        layout.addRow(tr("sup.f_name"), name)
        layout.addRow(tr("sup.f_contact"), contact)
        layout.addRow(tr("sup.f_email"), email)
        layout.addRow(tr("sup.f_phone"), phone)

        btn = QPushButton(tr("sup.btn_save"))
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
            QMessageBox.information(self, tr("msg.saved"), msg)
        else:
            QMessageBox.warning(self, tr("msg.save_error"), msg)

    def delete_selected_supplier(self):
        row = self.table_sup.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_supplier_delete")
            )
            return

        sup_id = int(self.table_sup.item(row, 0).text())
        sup_name = self.table_sup.item(row, 2).text()

        confirm = QMessageBox.question(
            self,
            tr("confirm.permanent_delete"),
            tr("confirm.delete_supplier", name=sup_name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.delete_supplier(sup_id)
            if success:
                QMessageBox.information(self, tr("msg.deleted"), msg)
                self.load_suppliers()
            else:
                QMessageBox.warning(self, tr("msg.error"), msg)

    # ------------------------------------------------------------------ #
    # CUSTOMERS TAB                                                       #
    # ------------------------------------------------------------------ #
    def init_customers_tab(self):
        layout = QVBoxLayout(self.tab_customers)

        toolbar = QHBoxLayout()
        btn_add = QPushButton(tr("cust.btn_add"))
        btn_add.clicked.connect(self.add_customer_dialog)
        btn_edit = QPushButton(tr("cust.btn_edit"))
        btn_edit.clicked.connect(lambda: self.edit_selected_customer())
        btn_delete = QPushButton(tr("cust.btn_delete"))
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self.delete_selected_customer)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_delete)
        layout.addLayout(toolbar)

        self.table_cust = QTableWidget()
        self.table_cust.setColumnCount(6)
        self.table_cust.setHorizontalHeaderLabels([
            tr("col.id"), tr("cust.col_code"), tr("cust.col_name"),
            tr("cust.col_contact"), tr("cust.col_email"), tr("cust.col_phone"),
        ])
        self.table_cust.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_cust.cellDoubleClicked.connect(self.edit_selected_customer)
        layout.addWidget(self.table_cust)
        self.load_customers()

    def load_customers(self):
        self.table_cust.setRowCount(0)
        db = SessionLocal()
        try:
            for cust in db.query(Customer).order_by(Customer.name).all():
                r = self.table_cust.rowCount()
                self.table_cust.insertRow(r)
                self.table_cust.setItem(r, 0, QTableWidgetItem(str(cust.id)))
                self.table_cust.setItem(r, 1, QTableWidgetItem(cust.code))
                self.table_cust.setItem(r, 2, QTableWidgetItem(cust.name))
                self.table_cust.setItem(r, 3, QTableWidgetItem(cust.contact_person or ""))
                self.table_cust.setItem(r, 4, QTableWidgetItem(cust.email or ""))
                self.table_cust.setItem(r, 5, QTableWidgetItem(cust.phone or ""))
        finally:
            db.close()

    def add_customer_dialog(self):
        self.customer_form(None)

    def edit_selected_customer(self, row=None, col=0):
        row = self.table_cust.currentRow() if row is None else row
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_customer_edit")
            )
            return
        cust_id = int(self.table_cust.item(row, 0).text())
        db = SessionLocal()
        try:
            cust = db.query(Customer).filter(Customer.id == cust_id).first()
        finally:
            db.close()
        if cust:
            self.customer_form(cust)

    def customer_form(self, customer):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("cust.dlg_edit") if customer else tr("cust.dlg_new"))
        layout = QFormLayout(dialog)

        code = QLineEdit(customer.code if customer else StockService.next_customer_code())
        name = QLineEdit(customer.name if customer else "")
        contact = QLineEdit(customer.contact_person or "" if customer else "")
        email = QLineEdit(customer.email or "" if customer else "")
        phone = QLineEdit(customer.phone or "" if customer else "")

        layout.addRow(tr("cust.f_code"), code)
        layout.addRow(tr("cust.f_name"), name)
        layout.addRow(tr("cust.f_contact"), contact)
        layout.addRow(tr("cust.f_email"), email)
        layout.addRow(tr("cust.f_phone"), phone)

        btn = QPushButton(tr("cust.btn_save"))
        btn.clicked.connect(lambda: self.save_customer(
            dialog, customer.id if customer else None,
            code.text(), name.text(), contact.text(), email.text(), phone.text(),
        ))
        layout.addRow(btn)
        dialog.exec()

    def save_customer(self, dialog, customer_id, code, name, contact, email, phone):
        if customer_id:
            success, msg = StockService.update_customer(customer_id, code, name, contact, email, phone)
        else:
            success, msg = StockService.add_customer(code, name, contact, email, phone)
        if success:
            dialog.accept()
            self.load_customers()
            QMessageBox.information(self, tr("msg.saved"), msg)
        else:
            QMessageBox.warning(self, tr("msg.save_error"), msg)

    def delete_selected_customer(self):
        row = self.table_cust.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_customer_delete")
            )
            return

        cust_id = int(self.table_cust.item(row, 0).text())
        cust_name = self.table_cust.item(row, 2).text()

        confirm = QMessageBox.question(
            self,
            tr("confirm.permanent_delete"),
            tr("confirm.delete_customer", name=cust_name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.delete_customer(cust_id)
            if success:
                QMessageBox.information(self, tr("msg.deleted"), msg)
                self.load_customers()
            else:
                QMessageBox.warning(self, tr("msg.error"), msg)

    # ------------------------------------------------------------------ #
    # PURCHASE ORDERS TAB                                                 #
    # ------------------------------------------------------------------ #
    def init_orders_tab(self):
        layout = QVBoxLayout(self.tab_orders)

        toolbar = QHBoxLayout()
        btn_add_order = QPushButton(tr("ord.btn_create"))
        btn_add_order.clicked.connect(self.create_order_dialog)

        btn_rec = QPushButton(tr("ord.btn_receive"))
        btn_rec.clicked.connect(self.receive_selected_order)

        btn_cancel = QPushButton(tr("ord.btn_cancel"))
        btn_cancel.clicked.connect(self.cancel_selected_order)

        btn_delete = QPushButton(tr("ord.btn_delete"))
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self.delete_order_permanently)

        toolbar.addWidget(btn_add_order)
        toolbar.addWidget(btn_rec)
        toolbar.addWidget(btn_cancel)
        toolbar.addWidget(btn_delete)
        layout.addLayout(toolbar)

        self.table_orders = QTableWidget()
        self.table_orders.setColumnCount(8)
        self.table_orders.setHorizontalHeaderLabels([
            tr("col.id"), tr("ord.col_ref"), tr("ord.col_supplier"),
            tr("ord.col_status"), tr("ord.col_total_ht"),
            tr("ord.col_total_ttc"), tr("ord.col_date"), tr("ord.col_payment"),
        ])
        self.table_orders.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_orders.itemSelectionChanged.connect(self.load_order_lines)
        self.table_orders.cellDoubleClicked.connect(self.show_order_details)
        layout.addWidget(self.table_orders)

        self.lbl_order_lines_title = QLabel(tr("ord.lines_title", ref=""))
        self.lbl_order_lines_title.setObjectName("lblSummary")
        layout.addWidget(self.lbl_order_lines_title)

        self.table_order_lines = QTableWidget()
        self.table_order_lines.setColumnCount(4)
        self.table_order_lines.setHorizontalHeaderLabels([
            tr("ord.details_col_product"), tr("ord.details_col_qty"),
            tr("ord.details_col_unit"), tr("ord.details_col_total"),
        ])
        self.table_order_lines.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_order_lines)

        self.lbl_orders_total = QLabel(tr("ord.total_label", total=0.0))
        self.lbl_orders_total.setObjectName("lblSummary")
        layout.addWidget(self.lbl_orders_total)
        self.load_orders()

    def load_order_lines(self):
        self.table_order_lines.setRowCount(0)
        row = self.table_orders.currentRow()
        if row < 0:
            self.lbl_order_lines_title.setText(tr("ord.lines_title", ref=""))
            return
        order_id = int(self.table_orders.item(row, 0).text())
        ref = self.table_orders.item(row, 1).text()
        self.lbl_order_lines_title.setText(tr("ord.lines_title", ref=ref))
        data = StockService.get_order_details(order_id)
        if not data:
            return
        for item_data in data["items"]:
            r = self.table_order_lines.rowCount()
            self.table_order_lines.insertRow(r)
            self.table_order_lines.setItem(r, 0, QTableWidgetItem(
                f"{item_data['sku']} - {item_data['name']}"
            ))
            self.table_order_lines.setItem(r, 1, QTableWidgetItem(str(item_data["quantity"])))
            self.table_order_lines.setItem(
                r, 2, QTableWidgetItem(f"{item_data['unit_cost']:.2f}")
            )
            self.table_order_lines.setItem(
                r, 3, QTableWidgetItem(f"{item_data['line_total']:.2f}")
            )
        if not data["items"]:
            self.table_order_lines.setRowCount(1)
            self.table_order_lines.setItem(0, 0, QTableWidgetItem(tr("ord.no_items")))

    def load_orders(self):
        self.table_orders.setRowCount(0)
        total_ttc = 0.0
        db = SessionLocal()
        try:
            orders = db.query(PurchaseOrder).order_by(PurchaseOrder.order_date.desc()).all()
            for o in orders:
                r = self.table_orders.rowCount()
                self.table_orders.insertRow(r)

                status_val = self._order_status_text(o.status)
                total_ht = o.total_excl_tax or 0.0
                vat_rate = o.vat_rate or 20.0
                ttc = total_ht * (1 + vat_rate / 100.0)
                total_ttc += ttc

                row_items = [
                    QTableWidgetItem(str(o.id)),
                    QTableWidgetItem(o.reference),
                    QTableWidgetItem(o.supplier.name if o.supplier else tr("status.unknown")),
                    QTableWidgetItem(status_val),
                    QTableWidgetItem(f"{total_ht:.2f}"),
                    QTableWidgetItem(f"{ttc:.2f}"),
                    QTableWidgetItem(o.order_date.strftime("%Y-%m-%d %H:%M") if o.order_date else ""),
                    QTableWidgetItem(
                        tr("pay.paid") if o.payment_status == StockService.PAYMENT_PAID
                        else tr("pay.pending")
                    ),
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
        self.lbl_orders_total.setText(tr("ord.total_label", total=total_ttc))

    def create_order_dialog(self):
        db = SessionLocal()
        try:
            suppliers = db.query(Supplier).order_by(Supplier.name).all()
            products = db.query(Product).order_by(Product.sku).all()
        finally:
            db.close()

        if not suppliers:
            QMessageBox.warning(self, tr("msg.warning"), tr("msg.need_supplier"))
            return
        if not products:
            QMessageBox.warning(self, tr("msg.warning"), tr("msg.need_product"))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("ord.dlg_create"))
        dialog.resize(680, 520)
        layout = QVBoxLayout(dialog)

        # Added seconds (%S) to avoid duplicate reference collisions
        unique_ref = f"PO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ref_input = QLineEdit(unique_ref)

        sup_combo = QComboBox()
        for s in suppliers:
            sup_combo.addItem(f"{s.code} - {s.name}", s.id)

        pay_combo = QComboBox()
        pay_combo.addItem(tr("pay.paid"), StockService.PAYMENT_PAID)
        pay_combo.addItem(tr("pay.pending"), StockService.PAYMENT_PENDING)

        form = QFormLayout()
        form.addRow(tr("ord.f_ref"), ref_input)
        form.addRow(tr("ord.f_supplier"), sup_combo)
        form.addRow(tr("pay.f_payment"), pay_combo)
        layout.addLayout(form)

        lines_box = QGroupBox(tr("ord.lines_header"))
        lv = QVBoxLayout(lines_box)

        product_by_id = {}
        dialog.prod_combo = QComboBox()
        for p in products:
            product_by_id[p.id] = p
            dialog.prod_combo.addItem(
                f"{p.sku} - {p.name} ({tr('ord.in_stock', qty=p.quantity or 0)})", p.id
            )
        dialog.qty_input = QLineEdit("1")
        dialog.unit_input = QLineEdit()

        def on_prod_change():
            p = product_by_id.get(dialog.prod_combo.currentData())
            if p:
                dialog.unit_input.setText(f"{p.purchase_price_excl_tax or 0.0:.2f}")

        dialog.prod_combo.currentIndexChanged.connect(on_prod_change)
        on_prod_change()

        entry = QHBoxLayout()
        entry.addWidget(dialog.prod_combo, 3)
        entry.addWidget(dialog.qty_input, 1)
        entry.addWidget(dialog.unit_input, 1)
        btn_add_line = QPushButton(tr("ord.btn_add_line"))
        btn_add_line.clicked.connect(lambda: self.add_order_line(dialog))
        entry.addWidget(btn_add_line, 1)
        lv.addLayout(entry)

        dialog.lines_table = QTableWidget()
        dialog.lines_table.setColumnCount(5)
        dialog.lines_table.setHorizontalHeaderLabels([
            tr("ord.details_col_product"), tr("ord.details_col_qty"),
            tr("ord.details_col_unit"), tr("ord.details_col_total"), "ID",
        ])
        dialog.lines_table.setColumnHidden(4, True)
        dialog.lines_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        dialog.lines_table.setMinimumHeight(180)
        lv.addWidget(dialog.lines_table)
        layout.addWidget(lines_box)

        dialog.lbl_new_total = QLabel(tr("ord.lbl_new_total", total=0.0))
        dialog.lbl_new_total.setObjectName("lblSummary")
        layout.addWidget(dialog.lbl_new_total)

        btn = QPushButton(tr("ord.btn_submit"))
        btn.clicked.connect(lambda: self.save_new_order(
            dialog, ref_input.text(), sup_combo.currentData(), pay_combo.currentData(),
        ))
        layout.addWidget(btn)
        dialog.exec()

    def add_order_line(self, dialog):
        try:
            qty = int(dialog.qty_input.text() or "1")
        except ValueError:
            QMessageBox.warning(dialog, tr("msg.input_error"), tr("msg.qty_whole"))
            return
        if qty <= 0:
            QMessageBox.warning(dialog, tr("msg.input_error"), tr("msg.qty_positive"))
            return
        try:
            unit = float(dialog.unit_input.text())
        except ValueError:
            QMessageBox.warning(dialog, tr("msg.input_error"), tr("msg.unit_number"))
            return
        if unit < 0:
            QMessageBox.warning(dialog, tr("msg.input_error"), tr("msg.unit_positive"))
            return

        pid = dialog.prod_combo.currentData()
        r = dialog.lines_table.rowCount()
        dialog.lines_table.insertRow(r)
        dialog.lines_table.setItem(r, 0, QTableWidgetItem(dialog.prod_combo.currentText()))
        dialog.lines_table.setItem(r, 1, QTableWidgetItem(str(qty)))
        dialog.lines_table.setItem(r, 2, QTableWidgetItem(f"{unit:.2f}"))
        dialog.lines_table.setItem(r, 3, QTableWidgetItem(f"{unit * qty:.2f}"))
        dialog.lines_table.setItem(r, 4, QTableWidgetItem(str(pid)))
        self.update_order_lines_total(dialog)

    def update_order_lines_total(self, dialog):
        total = 0.0
        for r in range(dialog.lines_table.rowCount()):
            try:
                total += float(dialog.lines_table.item(r, 3).text())
            except (TypeError, ValueError, AttributeError):
                continue
        dialog.lbl_new_total.setText(tr("ord.lbl_new_total", total=total))

    def save_new_order(self, dialog, ref, sup_id, payment_status="PAID"):
        items = []
        for r in range(dialog.lines_table.rowCount()):
            pid_item = dialog.lines_table.item(r, 4)
            if pid_item is None or not pid_item.text():
                continue
            try:
                qty = int(dialog.lines_table.item(r, 1).text())
                unit = float(dialog.lines_table.item(r, 2).text())
            except (ValueError, AttributeError):
                QMessageBox.warning(self, tr("msg.input_error"), tr("msg.qty_whole"))
                return
            if qty <= 0 or unit < 0:
                QMessageBox.warning(self, tr("msg.input_error"), tr("msg.qty_positive"))
                return
            items.append({
                "product_id": int(pid_item.text()),
                "quantity": qty,
                "unit_price": unit,
            })

        if not items:
            try:
                qty = int(dialog.qty_input.text() or "1")
                unit = float(dialog.unit_input.text())
            except ValueError:
                QMessageBox.warning(self, tr("msg.input_error"), tr("msg.qty_whole"))
                return
            if qty <= 0 or unit < 0:
                QMessageBox.warning(self, tr("msg.input_error"), tr("msg.qty_positive"))
                return
            items.append({
                "product_id": dialog.prod_combo.currentData(),
                "quantity": qty,
                "unit_price": unit,
            })

        success, msg = StockService.create_order(
            ref, sup_id, items,
            payment_status=payment_status,
        )
        if success:
            dialog.accept()
            self.load_orders()
            self.load_inventory()
            self.load_movements()
            self.load_order_lines()
            self.load_finance()
            QMessageBox.information(self, tr("msg.success"), msg)
        else:
            QMessageBox.warning(self, tr("msg.order_error"), msg)

    def receive_selected_order(self):
        row = self.table_orders.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_order_receive")
            )
            return
        order_id = int(self.table_orders.item(row, 0).text())
        success, msg = StockService.receive_order(order_id)
        if success:
            QMessageBox.information(self, tr("msg.success"), msg)
            self.load_orders()
            self.load_inventory()
            self.load_movements()
            self.load_finance()
        else:
            QMessageBox.warning(self, tr("msg.error"), msg)

    def cancel_selected_order(self):
        row = self.table_orders.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_order_cancel")
            )
            return

        order_id = int(self.table_orders.item(row, 0).text())

        reply = QMessageBox.question(
            self,
            tr("confirm.cancel_order"),
            tr("confirm.cancel_order_body"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            success, msg = StockService.cancel_or_return_order(order_id)
            if success:
                QMessageBox.information(self, tr("msg.cancelled"), msg)
                self.load_orders()
                self.load_inventory()
                self.load_movements()
                self.load_finance()
            else:
                QMessageBox.warning(self, tr("msg.error"), msg)

    def delete_order_permanently(self):
        row = self.table_orders.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_order_delete")
            )
            return

        order_id = int(self.table_orders.item(row, 0).text())
        order_ref = self.table_orders.item(row, 1).text()

        confirm = QMessageBox.question(
            self,
            tr("confirm.delete_order"),
            tr("confirm.delete_order_body", ref=order_ref),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.delete_order_permanently(order_id, revert_stock=True)
            if success:
                QMessageBox.information(self, tr("msg.deleted"), msg)
                self.load_orders()
                self.load_inventory()
                self.load_movements()
                self.load_finance()
            else:
                QMessageBox.warning(self, tr("msg.error"), msg)

    def show_order_details(self, row, col=0):
        if row < 0:
            return
        order_id = int(self.table_orders.item(row, 0).text())
        data = StockService.get_order_details(order_id)
        if not data:
            QMessageBox.warning(self, tr("msg.order_error"), tr("msg.order_not_found"))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("ord.details_title", ref=data["reference"]))
        dialog.resize(620, 380)
        layout = QVBoxLayout(dialog)

        status_val = self._order_status_text(data["status"])
        total_ttc = data["total_excl_tax"] * (1 + (data["vat_rate"] or 20.0) / 100.0)
        header = QLabel(
            tr(
                "ord.details_status",
                status=status_val,
                ht=data["total_excl_tax"],
                ttc=total_ttc,
            )
        )
        layout.addWidget(header)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels([
            tr("ord.details_col_product"), tr("ord.details_col_qty"),
            tr("ord.details_col_unit"), tr("ord.details_col_total"),
        ])
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
            table.setItem(0, 0, QTableWidgetItem(tr("ord.no_items")))
        layout.addWidget(table)

        btn_close = QPushButton(tr("ord.btn_close"))
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.exec()

    # ------------------------------------------------------------------ #
    # SALES & REFUNDS TAB                                                #
    # ------------------------------------------------------------------ #
    def init_sales_tab(self):
        layout = QVBoxLayout(self.tab_sales)

        toolbar = QHBoxLayout()
        btn_new_sale = QPushButton(tr("sal.btn_new"))
        btn_new_sale.clicked.connect(self.create_sale_dialog)

        btn_refund = QPushButton(tr("sal.btn_refund"))
        btn_refund.clicked.connect(self.refund_selected_sale)

        btn_paid = QPushButton(tr("sal.btn_mark_paid"))
        btn_paid.clicked.connect(self.mark_selected_sale_paid)

        btn_final = QPushButton(tr("sal.btn_final"))
        btn_final.clicked.connect(self.set_selected_sale_final)

        btn_delete = QPushButton(tr("sal.btn_delete"))
        btn_delete.setObjectName("btnDanger")
        btn_delete.clicked.connect(self.delete_sale_permanently)

        toolbar.addWidget(btn_new_sale)
        toolbar.addWidget(btn_refund)
        toolbar.addWidget(btn_paid)
        toolbar.addWidget(btn_final)
        toolbar.addWidget(btn_delete)
        layout.addLayout(toolbar)

        self.table_sales = QTableWidget()
        self.table_sales.setColumnCount(12)
        self.table_sales.setHorizontalHeaderLabels([
            tr("col.id"), tr("sal.col_ref"), tr("sal.col_product"),
            tr("sal.col_qty"), tr("sal.col_unit_price"),
            tr("sal.col_total_ttc"), tr("sal.col_date"),
            tr("sal.col_status"), tr("sal.col_refund_date"),
            tr("sal.col_customer"), tr("sal.col_payment"), tr("sal.col_final"),
        ])
        self.table_sales.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_sales)

        self.lbl_sales_total = QLabel(
            tr("sal.total_label", sold=0.0, refunded=0.0, net=0.0,
               sold_count=0, refunded_count=0)
        )
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
                status_val = self._sale_status_text(s.status)

                row_items = [
                    QTableWidgetItem(str(s.id)),
                    QTableWidgetItem(s.reference),
                    QTableWidgetItem(
                        f"{s.product.sku if s.product else 'N/A'} - "
                        f"{s.product.name if s.product else tr('status.unknown')}"
                    ),
                    QTableWidgetItem(str(s.quantity)),
                    QTableWidgetItem(f"{s.unit_price_excl_tax or 0.0:.2f}"),
                    QTableWidgetItem(f"{total_ttc:.2f}"),
                    QTableWidgetItem(s.sale_date.strftime("%Y-%m-%d %H:%M") if s.sale_date else ""),
                    QTableWidgetItem(status_val),
                    QTableWidgetItem(s.refund_date.strftime("%Y-%m-%d %H:%M") if s.refund_date else ""),
                    QTableWidgetItem(s.customer.name if s.customer else ""),
                    QTableWidgetItem(
                        tr("pay.paid") if s.payment_status == StockService.PAYMENT_PAID
                        else tr("pay.pending")
                    ),
                    QTableWidgetItem(
                        tr("generic.yes") if s.refundable is False else tr("generic.no")
                    ),
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
            tr(
                "sal.total_label",
                sold=summary["total_sold_ttc"],
                refunded=summary["total_refunded_ttc"],
                net=net,
                sold_count=summary["sold_count"],
                refunded_count=summary["refunded_count"],
            )
        )

    def sell_from_inventory(self):
        row = self.table_inv.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_product_first")
            )
            return
        self.create_sale_dialog(preselected_product_id=int(self.table_inv.item(row, 0).text()))

    def create_sale_dialog(self, preselected_product_id=None):
        db = SessionLocal()
        try:
            products = db.query(Product).order_by(Product.sku).all()
            customers = db.query(Customer).order_by(Customer.name).all()
        finally:
            db.close()

        if not products:
            QMessageBox.warning(self, tr("msg.warning"), tr("msg.need_product"))
            return

        price_map = {p.id: (p.selling_price_excl_tax or 0.0) for p in products}

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("sal.dlg_new"))
        layout = QFormLayout(dialog)

        unique_ref = f"SA-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ref_input = QLineEdit(unique_ref)

        prod_combo = QComboBox()
        for p in products:
            prod_combo.addItem(
                f"{p.sku} - {p.name} ({tr('sal.in_stock', qty=p.quantity or 0)})", p.id
            )

        cust_combo = QComboBox()
        cust_combo.addItem(tr("sal.customer_none"), None)
        for c in customers:
            cust_combo.addItem(f"{c.code} - {c.name}", c.id)

        pay_combo = QComboBox()
        pay_combo.addItem(tr("pay.paid"), StockService.PAYMENT_PAID)
        pay_combo.addItem(tr("pay.pending"), StockService.PAYMENT_CREDIT)

        date_edit = QDateEdit(QDate.currentDate())
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("yyyy-MM-dd")

        final_check = QCheckBox(tr("sal.chk_final"))

        qty_input = QLineEdit("1")
        unit_price = QLineEdit()
        vat = QLineEdit("20")
        lbl_total = QLabel(tr("sal.total_ttc", total=0.0))
        lbl_total.setStyleSheet("font-weight: bold; color: #107c41;")

        def update_total():
            try:
                q = int(qty_input.text() or "0")
                p = float(unit_price.text() or "0")
                v = float(vat.text() or "0")
                lbl_total.setText(tr("sal.total_ttc", total=p * q * (1 + v / 100.0)))
            except ValueError:
                lbl_total.setText(tr("sal.total_ttc", total=0.0))

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

        layout.addRow(tr("sal.f_ref"), ref_input)
        layout.addRow(tr("dlg.f_product"), prod_combo)
        layout.addRow(tr("sal.f_customer"), cust_combo)
        layout.addRow(tr("sal.f_date"), date_edit)
        layout.addRow(tr("sal.f_qty"), qty_input)
        layout.addRow(tr("sal.f_unit_price"), unit_price)
        layout.addRow(tr("sal.f_vat"), vat)
        layout.addRow(tr("pay.f_payment"), pay_combo)
        layout.addRow(final_check)
        layout.addRow(lbl_total)

        btn = QPushButton(tr("sal.btn_record"))
        btn.clicked.connect(lambda: self.save_new_sale(
            dialog, ref_input.text(), prod_combo.currentData(),
            qty_input.text(), unit_price.text(), vat.text(),
            cust_combo.currentData(), pay_combo.currentData(),
            date_edit.date().toPython(), final_check.isChecked(),
        ))
        layout.addRow(btn)
        dialog.exec()

    def save_new_sale(self, dialog, ref, prod_id, qty_text, price_text, vat_text,
                      customer_id=None, payment_status="PAID",
                      sale_date=None, refundable=True):
        success, msg = StockService.create_sale(
            ref, prod_id, qty_text, price_text, vat_text,
            customer_id=customer_id, payment_status=payment_status,
            sale_date=sale_date, refundable=refundable,
        )
        if success:
            dialog.accept()
            self.load_sales()
            self.load_inventory()
            self.load_movements()
            self.load_finance()
            QMessageBox.information(self, tr("msg.sale_recorded"), msg)
        else:
            QMessageBox.warning(self, tr("msg.sale_error"), msg)

    def mark_selected_sale_paid(self):
        row = self.table_sales.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_sale_paid")
            )
            return

        sale_id = int(self.table_sales.item(row, 0).text())
        sale_ref = self.table_sales.item(row, 1).text()

        confirm = QMessageBox.question(
            self,
            tr("confirm.mark_paid"),
            tr("confirm.mark_paid_body", ref=sale_ref),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.mark_sale_paid(sale_id)
            if success:
                QMessageBox.information(self, tr("msg.success"), msg)
                self.load_sales()
                self.load_finance()
            else:
                QMessageBox.warning(self, tr("msg.error"), msg)

    def set_selected_sale_final(self):
        row = self.table_sales.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_sale_final")
            )
            return

        sale_id = int(self.table_sales.item(row, 0).text())
        sale_ref = self.table_sales.item(row, 1).text()
        already_final = self.table_sales.item(row, 11).text() == tr("generic.yes")

        if already_final:
            QMessageBox.information(self, tr("msg.info"), tr("msg.sale_already_final", ref=sale_ref))
            return

        confirm = QMessageBox.question(
            self,
            tr("confirm.final_sale"),
            tr("confirm.final_sale_body", ref=sale_ref),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.set_sale_final(sale_id, final=True)
            if success:
                QMessageBox.information(self, tr("msg.success"), msg)
                self.load_sales()
                self.load_finance()
            else:
                QMessageBox.warning(self, tr("msg.error"), msg)

    def refund_selected_sale(self):
        row = self.table_sales.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_sale_refund")
            )
            return

        sale_id = int(self.table_sales.item(row, 0).text())
        sale_ref = self.table_sales.item(row, 1).text()

        confirm = QMessageBox.question(
            self,
            tr("confirm.refund_sale"),
            tr("confirm.refund_sale_body", ref=sale_ref),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.refund_sale(sale_id)
            if success:
                QMessageBox.information(self, tr("msg.refunded"), msg)
                self.load_sales()
                self.load_inventory()
                self.load_movements()
                self.load_finance()
            else:
                QMessageBox.warning(self, tr("msg.refund_error"), msg)

    def delete_sale_permanently(self):
        row = self.table_sales.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, tr("msg.selection_required"), tr("msg.select_sale_delete")
            )
            return

        sale_id = int(self.table_sales.item(row, 0).text())
        sale_ref = self.table_sales.item(row, 1).text()

        confirm = QMessageBox.question(
            self,
            tr("confirm.delete_sale"),
            tr("confirm.delete_sale_body", ref=sale_ref),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )

        if confirm == QMessageBox.Yes:
            success, msg = StockService.delete_sale_permanently(sale_id, revert_stock=True)
            if success:
                QMessageBox.information(self, tr("msg.deleted"), msg)
                self.load_sales()
                self.load_inventory()
                self.load_movements()
                self.load_finance()
            else:
                QMessageBox.warning(self, tr("msg.error"), msg)

    # ------------------------------------------------------------------ #
    # STOCK LOG TAB                                                       #
    # ------------------------------------------------------------------ #
    def init_movements_tab(self):
        layout = QVBoxLayout(self.tab_movements)

        cards = QGridLayout()
        cards.setHorizontalSpacing(10)
        cards.setVerticalSpacing(10)
        card_defs = [
            ("total_movements", tr("mov.card_movements"), "#1d4ed8", False),
            ("items_sold", tr("mov.card_sold_items"), "#1e7e34", False),
            ("stock_on_hand", tr("mov.card_on_hand"), "#0f766e", False),
            ("revenue_ttc", tr("mov.card_revenue"), "#107c41", True),
            ("pending_ttc", tr("mov.card_pending"), "#b45309", True),
            ("refunded_ttc", tr("mov.card_refunded"), "#6b7280", True),
        ]
        self.mov_cards = {}
        for i, (key, title, color, is_money) in enumerate(card_defs):
            card = QLabel("")
            card.setObjectName("lblCard")
            card.setTextFormat(Qt.RichText)
            self.mov_cards[key] = (card, color, is_money)
            cards.addWidget(card, i // 3, i % 3)
        layout.addLayout(cards)

        self.search_mov = QLineEdit()
        self.search_mov.setPlaceholderText(tr("mov.search_placeholder"))
        self.search_mov.textChanged.connect(self.filter_movements)
        layout.addWidget(self.search_mov)

        self.table_mov = QTableWidget()
        self.table_mov.setColumnCount(6)
        self.table_mov.setHorizontalHeaderLabels([
            tr("mov.col_date"), tr("mov.col_product"), tr("mov.col_type"),
            tr("mov.col_qty"), tr("mov.col_ref"), tr("mov.col_balance"),
        ])
        self.table_mov.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_mov)
        self.load_movements()

    def _mov_card_html(self, title, value, color):
        return (
            f'<div style="font-size:11px; color:#6b7280;">{title}</div>'
            f'<div style="font-size:22px; font-weight:bold; color:{color};">'
            f'{value}</div>'
        )

    def refresh_movements_summary(self):
        data = StockService.get_stock_log_summary()
        for key, (card, color, is_money) in self.mov_cards.items():
            value = data.get(key, 0)
            text = f"{value:,.2f}" if is_money else f"{value:,}"
            if is_money:
                text = f"${text}"
            title = tr(
                {
                    "total_movements": "mov.card_movements",
                    "items_sold": "mov.card_sold_items",
                    "stock_on_hand": "mov.card_on_hand",
                    "revenue_ttc": "mov.card_revenue",
                    "pending_ttc": "mov.card_pending",
                    "refunded_ttc": "mov.card_refunded",
                }[key]
            )
            card.setText(self._mov_card_html(title, text, color))

    def load_movements(self):
        self.table_mov.setRowCount(0)
        db = SessionLocal()
        try:
            movements = db.query(StockMovement).order_by(StockMovement.created_at.desc()).all()
            balances = {p.id: p.quantity or 0 for p in db.query(Product).all()}
            signs = {
                MovementType.INBOUND: 1,
                MovementType.ORDER_RECEIPT: 1,
                MovementType.SALE_REFUND: 1,
                MovementType.OUTBOUND: -1,
                MovementType.SALE: -1,
                MovementType.SUPPLIER_RETURN: -1,
                MovementType.ADJUSTMENT: -1,
            }
            for m in movements:
                r = self.table_mov.rowCount()
                self.table_mov.insertRow(r)
                self.table_mov.setItem(r, 0, QTableWidgetItem(
                    m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else ""
                ))
                self.table_mov.setItem(r, 1, QTableWidgetItem(m.product.sku if m.product else "N/A"))
                self.table_mov.setItem(
                    r, 2,
                    QTableWidgetItem(tr(f"mov.{m.type.name}") if m.type else ""),
                )
                self.table_mov.setItem(r, 3, QTableWidgetItem(str(m.quantity)))
                self.table_mov.setItem(r, 4, QTableWidgetItem(m.reference or ""))
                pid = m.product_id
                if pid is not None and pid in balances:
                    balance_item = QTableWidgetItem(str(balances[pid]))
                    balance_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table_mov.setItem(r, 5, balance_item)
                    balances[pid] -= signs.get(m.type, 0) * (m.quantity or 0)
                else:
                    self.table_mov.setItem(r, 5, QTableWidgetItem(""))
        finally:
            db.close()
        self.refresh_movements_summary()

    def filter_movements(self, text):
        text = text.lower()
        for row in range(self.table_mov.rowCount()):
            sku = (self.table_mov.item(row, 1).text() or "").lower()
            mtype = (self.table_mov.item(row, 2).text() or "").lower()
            ref = (self.table_mov.item(row, 4).text() or "").lower()
            self.table_mov.setRowHidden(row, not (text in sku or text in mtype or text in ref))

    # ------------------------------------------------------------------ #
    # FINANCE TAB                                                         #
    # ------------------------------------------------------------------ #
    def init_finance_tab(self):
        layout = QVBoxLayout(self.tab_finance)

        filters = QHBoxLayout()
        self.fin_all_time = QCheckBox(tr("f.all_time"))
        self.fin_all_time.setChecked(True)
        self.fin_all_time.stateChanged.connect(self.load_finance)

        self.fin_from = QDateEdit(QDate.currentDate().addMonths(-12))
        self.fin_from.setCalendarPopup(True)
        self.fin_from.setDisplayFormat("yyyy-MM-dd")
        self.fin_from.dateChanged.connect(self.load_finance)

        self.fin_to = QDateEdit(QDate.currentDate())
        self.fin_to.setCalendarPopup(True)
        self.fin_to.setDisplayFormat("yyyy-MM-dd")
        self.fin_to.dateChanged.connect(self.load_finance)

        self.fin_kind = QComboBox()
        self.fin_kind.addItem(tr("f.kind_all"), "all")
        self.fin_kind.addItem(tr("f.kind_suppliers"), "supplier")
        self.fin_kind.addItem(tr("f.kind_customers"), "customer")
        self.fin_kind.currentIndexChanged.connect(self.load_finance)

        btn_refresh = QPushButton(tr("f.btn_refresh"))
        btn_refresh.clicked.connect(self.load_finance)

        filters.addWidget(self.fin_all_time)
        filters.addWidget(QLabel(tr("f.from")))
        filters.addWidget(self.fin_from)
        filters.addWidget(QLabel(tr("f.to")))
        filters.addWidget(self.fin_to)
        filters.addWidget(QLabel(tr("f.show")))
        filters.addWidget(self.fin_kind)
        filters.addStretch(1)
        filters.addWidget(btn_refresh)
        layout.addLayout(filters)

        grid = QGridLayout()
        grid.setSpacing(8)
        titles = [
            ("f.card_revenue", "revenue_net", "#107c41"),
            ("f.card_confirmed", "confirmed", "#1e7e34"),
            ("f.card_pending_refund", "pending_refund", "#b45309"),
            ("f.card_credit", "credit_pending", "#b45309"),
            ("f.card_refunded", "refunded", "#6b7280"),
            ("f.card_inbound", "inbound", "#0f766e"),
            ("f.card_inbound_pending", "inbound_pending", "#b45309"),
            ("f.card_orders_unpaid", "orders_unpaid", "#b45309"),
            ("f.card_net", "net_result", "#dc2626"),
        ]
        self.fin_cards = {}
        for idx, (key, field, fg) in enumerate(titles):
            card = QLabel()
            card.setObjectName("lblCard")
            card.setAlignment(Qt.AlignCenter)
            self.fin_cards[field] = card
            self.fin_card_fg = getattr(self, "fin_card_fg", {})
            self.fin_card_fg[field] = fg
            grid.addWidget(card, idx // 5, idx % 5)
        layout.addLayout(grid)

        self.table_fin = QTableWidget()
        self.table_fin.setColumnCount(7)
        self.table_fin.setHorizontalHeaderLabels([
            tr("f.col_date"), tr("f.col_direction"), tr("f.col_ref"),
            tr("f.col_pending"), tr("f.col_kind"), tr("f.col_partner"),
            tr("f.col_amount"),
        ])
        self.table_fin.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_fin)

        self.lbl_fin_empty = QLabel()
        self.lbl_fin_empty.setObjectName("lblSummary")
        layout.addWidget(self.lbl_fin_empty)
        self.load_finance()

    def _card_html(self, field, amount):
        color = self.fin_card_fg.get(field, "#107c41")
        if field == "net_result":
            color = "#1e7e34" if amount >= 0 else "#dc2626"
        title = tr(f"f.card_{field}")
        return (
            f"<div style='color:#6b7280;font-size:11px;'>{title}</div>"
            f"<div style='color:{color};font-size:18px;font-weight:bold;'>"
            f"${amount:,.2f}</div>"
        )

    def load_finance(self):
        if not hasattr(self, "fin_cards"):
            return
        from_date = None
        to_date = None
        if not self.fin_all_time.isChecked():
            from_date = self.fin_from.date().toPython()
            to_date = self.fin_to.date().toPython()
        kind = self.fin_kind.currentData()
        data = StockService.get_finance_data(from_date, to_date, kind)

        for field, card in self.fin_cards.items():
            card.setText(self._card_html(field, data.get(field, 0.0)))

        self.table_fin.setRowCount(0)
        for ln in data["lines"]:
            r = self.table_fin.rowCount()
            self.table_fin.insertRow(r)
            date_str = ln["date"].strftime("%Y-%m-%d %H:%M") if ln["date"] else ""
            direction = (
                tr("f.direction_inbound") if ln["direction"] == "INBOUND"
                else tr("f.direction_outbound")
            )
            kind_text = (
                tr("f.kind_supplier") if ln["kind"] == "supplier"
                else tr("f.kind_customer")
            )
            pending_text = tr("f.pending_yes") if ln["pending"] else tr("f.pending_no")
            amount_item = QTableWidgetItem(f"{ln['amount']:,.2f}")
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            cells = [
                QTableWidgetItem(date_str),
                QTableWidgetItem(direction),
                QTableWidgetItem(ln["reference"]),
                QTableWidgetItem(pending_text),
                QTableWidgetItem(kind_text),
                QTableWidgetItem(ln["partner"]),
                amount_item,
            ]
            if ln["direction"] == "INBOUND":
                for c in cells[:6]:
                    c.setBackground(QColor("#ecfeff"))
            if ln["pending"]:
                cells[3].setForeground(QColor("#b45309"))
            if ln["note"] == "REFUNDED":
                for c in cells:
                    c.setForeground(QColor("#9ca3af"))
                    c.setBackground(QColor("#f8fafc"))
            for col, cell in enumerate(cells):
                self.table_fin.setItem(r, col, cell)

        if not data["lines"]:
            self.table_fin.setRowCount(1)
            self.table_fin.setItem(0, 0, QTableWidgetItem(tr("f.no_data")))
            self.lbl_fin_empty.setText("")
        else:
            self.lbl_fin_empty.setText(
                tr(
                    "f.total_lines",
                    count=len(data["lines"]),
                    revenue=data["revenue_net"],
                    inbound=data["inbound"],
                    net=data["net_result"],
                )
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(QPalette.PlaceholderText, QColor("#8b95a5"))
    palette.setColor(QPalette.Text, QColor("#1f2937"))
    palette.setColor(QPalette.ButtonText, QColor("#111827"))
    palette.setColor(QPalette.WindowText, QColor("#111827"))
    app.setPalette(palette)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())