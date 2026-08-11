# Gestionnaire de Stock (Inventory & Purchase Order Manager)

Application de bureau **PySide6** pour gérer l'inventaire, les fournisseurs, les commandes d'achat, les ventes et les remboursements d'un commerce (thème Excel blanc).

Base de données **SQLite** (fichier `stock_management.db`, créé automatiquement au premier lancement) via SQLAlchemy.

---

## Fonctionnalités

| Onglet | Description |
|--------|-------------|
| **Inventory & VAT** | Produits (SKU, catégorie, stock, seuil d'alerte, prix HT/TTC, TVA 20 %), recherche, ajustement de stock, vente rapide, suppression avec confirmation, alerte stock bas (lignes rouges), résumé (valeur du stock TTC, alertes) |
| **Suppliers** | Ajout / édition / suppression de fournisseurs (code, contact, e-mail, téléphone), contrôle des doublons |
| **Purchase Orders** | Création de commandes fournisseurs (référence unique auto), réception (incrémente le stock), annulation/retour (décrémente le stock), suppression permanente, détails au double-clic, couleurs par statut, total sous le tableau |
| **Sales & Refunds** | Enregistrement de ventes (déduit le stock), **retour / remboursement sous 14 jours** (restaure le stock, refusé au-delà de 14 jours ou si déjà remboursé), suppression permanente, total des ventes/remboursements/net sous le tableau |
| **Stock Log** | Journal de tous les mouvements (entrée, sortie, réception de commande, retour fournisseur, vente, remboursement, ajustement) avec filtrage |

Autres fonctionnalités :
- **Import / Export Excel** (`.xlsx`) avec colonnes calculées (montant TVA, prix TTC, statut) et validation des colonnes requises.
- Validation de toutes les saisies (quantités, prix, doublons SKU/référence, stock insuffisant) avec messages d'erreur explicites.
- Intégrité des données : clés étrangères activées — suppression bloquée si un produit/fournisseur est référencé ailleurs.

---

## Installation

```bash
# 1. Créer un environnement virtuel (recommandé)
python -m venv .venv

# 2. Activer l'environnement
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Lancer l'application
python stock.py
```

Dépendances : `PySide6`, `SQLAlchemy`, `pandas`, `openpyxl` (voir `requirements.txt`).

---

## Utilisation rapide

1. **Fournisseurs** : ajoutez d'abord un fournisseur (`+ Add Supplier`).
2. **Produits** : ajoutez des produits avec prix d'achat/vente HT, TVA et seuil d'alerte (`+ Add Product`).
3. **Commandes** : créez une commande fournisseur, puis `Receive Order` pour incrémenter le stock.
4. **Ventes** : `+ New Sale` (ou `Sell Product` dans l'inventaire) pour vendre et décrémenter le stock.
5. **Remboursements** : sélectionnez une vente de moins de 14 jours → `Return / Refund (14 days)`.
6. **Excel** : exportez/importez l'inventaire via les boutons `Export Excel` / `Import Excel`.

---

## Structure du projet

```
Gestionnaire_de_stock/
├── DBase.py        # Modèles SQLAlchemy + base SQLite + énumérations (statuts, mouvements)
├── services.py     # Logique métier (produits, fournisseurs, commandes, ventes, Excel)
├── stock.py        # Interface graphique PySide6 (point d'entrée)
├── requirements.txt
└── stock_management.db  # Base de données (créée automatiquement)
```

---

## Licence

Projet personnel — utilisation libre.
