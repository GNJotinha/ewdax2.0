import streamlit as st
import bcrypt

USUARIOS = st.secrets.get("USUARIOS", {})

def autenticar(usuario, senha):
    user = USUARIOS.get(usuario)
    if not user:
        return False
    senha_hash = user.get("senha_hash", "")
    if not senha_hash:
        return False
    try:
        return bcrypt.checkpw(senha.encode(), senha_hash.encode())
    except Exception:
        return False
