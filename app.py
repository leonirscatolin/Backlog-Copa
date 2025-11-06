import streamlit as st
import time

# URL do seu novo servidor 'socorro'
REDIRECT_URL = "http://64.181.176.162:8501/"

st.set_page_config(page_title="Redirecionando...", layout="centered")

st.warning("### Você está sendo redirecionado...")
st.markdown(f"""
O nosso sistema de dashboard foi movido para um novo servidor mais rápido.

Por favor, aguarde enquanto redirecionamos você.
""")

# Link para o usuário clicar (fallback)
st.markdown(f"Se você não for redirecionado em 3 segundos, [clique aqui]({REDIRECT_URL}).")

# O código de "magia" do redirecionamento (Meta Refresh)
st.markdown(f'<meta http-equiv="refresh" content="3; url={REDIRECT_URL}">', unsafe_allow_html=True)

# Prende o app por um tempo para o usuário ler a mensagem
time.sleep(10)
