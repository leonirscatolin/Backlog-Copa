import streamlit as st
import streamlit.components.v1 as components
import time

REDIRECT_URL = "http://64.181.176.162:8501/"

st.set_page_config(page_title="Redirecionando...", layout="centered")

st.warning("### Você está sendo redirecionado...")

st.markdown("""
O dashboard foi movido para um novo servidor.
""") 

st.markdown(f"Acesse o novo dashboard [aqui]({REDIRECT_URL}).")

js_redirect = f"""
    <script>
        setTimeout(function() {{
            window.location.href = "{REDIRECT_URL}";
        }}, 3000);
    </script>
"""
components.html(js_redirect, height=0)

time.sleep(10)
