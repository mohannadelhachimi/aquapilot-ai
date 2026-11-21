import streamlit as st
from PIL import Image
from core.auth import authenticate

try:
    logo = Image.open("assets/logo.png")
except FileNotFoundError:
    logo = "💧"

st.set_page_config(page_title="AquaPilot AI", page_icon=logo, layout="wide")

from ui.style import inject_css, hero, FARM_NAV, REGIONAL_NAV

inject_css()
if not isinstance(logo, str):
    st.logo(logo)


def login_page():
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        hero(
            "AquaPilot AI",
            "Gestion intelligente de l'eau pour les Provinces du Sud du Maroc",
            ["Dakhla", "Laâyoune", "Guelmim"],
        )
        with st.container(border=True):
            username = st.text_input("Identifiant")
            password = st.text_input("Mot de passe", type="password")
            if st.button("Se connecter", type="primary", use_container_width=True):
                user = authenticate(username, password)
                if user:
                    st.session_state["user"] = user
                    st.rerun()
                else:
                    st.error("Identifiant ou mot de passe incorrect.")
        st.info("Démo : admin / admin123  ·  ferme1 / demo123")


user = st.session_state.get("user")

if user is None:
    pg = st.navigation([st.Page(login_page, title="Connexion", icon="🔐")], position="hidden")
elif user["role"] == "admin":
    pg = st.navigation({
        "Administration": [
            st.Page("views/regional.py", title="Dashboard régional", icon="🗺️"),
        ]
    }, position="hidden")
else:
    pg = st.navigation({
        "Mon exploitation": [
            st.Page("views/farm.py", title="Dashboard agricole", icon="🌱"),
        ]
    }, position="hidden")

if user:
    with st.sidebar:
        side_logo_col, side_text_col = st.columns([0.3, 0.7], vertical_alignment="center")
        with side_logo_col:
            if not isinstance(logo, str):
                st.image(logo, width=50)
        with side_text_col:
            st.markdown(f"**{user['name']}**")
            st.caption(f"Rôle : {user['role']}")

        st.markdown("---")
        if user["role"] == "admin":
            st.markdown("**Sections**")
            st.radio("Sections", REGIONAL_NAV, key="regional_nav", label_visibility="collapsed")
        else:
            st.markdown("**Modules**")
            st.radio("Modules", FARM_NAV, key="farm_nav", label_visibility="collapsed")

        st.markdown("---")
        if st.button("Se déconnecter", use_container_width=True):
            st.session_state.clear()
            st.rerun()

pg.run()
