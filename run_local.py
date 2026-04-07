# -*- coding: utf-8 -*-
"""
Created on Tue Apr  7 09:28:30 2026

@author: chloe
"""
import os

# ── Paramètres locaux ──────────────────────────────────────────────────────────
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://todo_user:todo_password@localhost:5432/todo_db"
)
os.environ.setdefault("SECRET_KEY", "dev-secret-key-local")

# ── Créer les tables si elles n'existent pas encore ───────────────────────────
from database import engine, Base
import models  # noqa: charge les modèles
Base.metadata.create_all(bind=engine)
print("✅ Tables créées / vérifiées.")

# ── Démarrer uvicorn ───────────────────────────────────────────────────────────
import uvicorn
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=3087, reload=True)


























