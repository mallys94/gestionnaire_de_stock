# Gestionnaire de Stock (Inventory & Purchase Order Manager)

Application de bureau **PySide6** pour gérer l'inventaire, les fournisseurs, les commandes d'achat, les ventes et les remboursements d'un commerce (thème Excel blanc).

Base de données **SQLite** (fichier `stock_management.db`, créé automatiquement au premier lancement) via SQLAlchemy.

---

## Fonctionnalités

| Onglet | Description |
|--------|-------------|
| **Inventory & VAT** | Produits (SKU, catégorie, stock, seuil d'alerte, prix HT/TTC, TVA 20 %), recherche, ajustement de stock **en valeur absolue** (on saisit le stock final exact, la différence est enregistrée en mouvement), vente rapide, suppression avec confirmation, alerte stock bas (lignes rouges), résumé (valeur du stock TTC, alertes) |
| **Suppliers** | Ajout / édition / suppression de fournisseurs (code, contact, e-mail, téléphone), contrôle des doublons |
| **Purchase Orders** | Création de commandes multi-lignes (article commandé, quantité, **prix unitaire**, **total ligne**, total de la commande) ; la création d'une commande **ajoute immédiatement les quantités au stock** ; `Receive Order` ne fait que confirmer la réception (pas de double comptage) ; annulation/retour ou suppression **décrémente** le stock ; tableau de lignes de la commande sélectionnée visible dans l'onglet, couleurs par statut, total sous le tableau |
| **Sales & Refunds** | Enregistrement de ventes (déduit le stock), **retour / remboursement sous 14 jours** (restaure le stock, refusé au-delà de 14 jours ou si déjà remboursé), suppression permanente, total des ventes/remboursements/net sous le tableau |
| **Customers** | Ajout / édition / suppression de clients, liaison client lors des ventes |
| **Stock Log** | Journal de tous les mouvements (entrée, sortie, réception de commande, retour fournisseur, vente, remboursement, ajustement) avec **colonne « Stock après »** (solde du produit après chaque mouvement) + **cartes de synthèse** (mouvements, articles vendus/reçus, revenus, en attente, remboursés) |
| **Finance** | Tableau de bord financier : revenus confirmés/en attente de remboursement, crédits impayés, commandes reçues/en cours et impayées, résultat net ; filtres par période et par type de partenaire |

Autres fonctionnalités :
- **Multilingue (i18n)** : anglais (EN), français (FR), allemand (DE) et espagnol (ES). Sélecteur de langue en haut de la fenêtre (coin supérieur droit). Le choix est mémorisé via `QSettings` et restauré au prochain lancement.
- **Import / Export Excel** (`.xlsx`) avec colonnes calculées (montant TVA, prix TTC, statut) et validation des colonnes requises.
- **Sauvegardes automatiques** : copie cohérente de la base SQLite (via l'API de sauvegarde en ligne de SQLite) au démarrage, à la fermeture et via le bouton **Backup DB**, dans le dossier `backups/` (les 10 plus récentes conservées, dossier personnalisable via la variable d'environnement `STOCK_BACKUP_DIR`).
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
3. **Commandes** : créez une commande (article, quantité, prix unitaire), le stock est incrémenté immédiatement ; `Receive Order` confirme la réception.
4. **Ventes** : `+ New Sale` (ou `Sell Product` dans l'inventaire) pour vendre et décrémenter le stock.
5. **Remboursements** : sélectionnez une vente de moins de 14 jours → `Return / Refund (14 days)`.
6. **Excel** : exportez/importez l'inventaire via les boutons `Export Excel` / `Import Excel`.

---

## Structure du projet

```
Gestionnaire_de_stock/
├── DBase.py        # Modèles SQLAlchemy + base SQLite + énumérations (statuts, mouvements)
├── i18n.py         # Couche de traduction (EN / FR / DE / ES) + persistance de la langue
├── services.py     # Logique métier (produits, fournisseurs, commandes, ventes, Excel)
├── stock.py        # Interface graphique PySide6 (point d'entrée)
├── requirements.txt
└── stock_management.db  # Base de données (créée automatiquement)
```

### Multilingue

L'application embarque une couche de traduction légère (`i18n.py`) :

- `tr("clé", **kwargs)` renvoie le texte localisé (les clés non trouvées retombent en anglais via le mécanisme de repli).
- `set_language()` / `get_language()` / `load_language()` / `save_language()` gèrent la langue active et sa persistance.
- Langues prises en charge : `en`, `fr`, `de`, `es` (sélectionnables dans le coin supérieur droit de la fenêtre).

> Note : les références des mouvements de stock (journal) sont enregistrées en base dans la langue active au moment de l'opération ; les lignes historiques conservent donc la langue de leur création.

---

## Licence

Projet personnel — utilisation libre.
