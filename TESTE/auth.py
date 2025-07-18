import streamlit as st
USUARIOS = st.secrets.get("USUARIOS", {})

def autenticar(usuario, senha):
    return usuario in USUARIOS and USUARIOS[usuario]["senha"] == senha
