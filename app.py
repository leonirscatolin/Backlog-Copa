import streamlit as st
import streamlit.components.v1 as components
import time

# URL do seu novo servidor 'socorro'
REDIRECT_URL = "http://64.181.176.162:8501/"

st.set_page_config(page_title="Redirecionando...", layout="centered")

st.warning("### Você está sendo redirecionado...")
st.markdown(f"""
O dashboard foi movido para um novo servidor.

# Link para o usuário clicar (fallback)
st.markdown(f"Acesse o novo dashboard [aqui]({REDIRECT_URL}).")

# O novo "truque" de redirecionamento (JavaScript)
js_redirect = f"""
    <script>
        setTimeout(function() {{
            window.location.href = "{REDIRECT_URL}";
        }}, 3000); // 3000 milissegundos = 3 segundos
    </script>
"""
components.html(js_redirect, height=0)

# Prende o app por um tempo para o usuário ler a mensagem
time.sleep(10)
