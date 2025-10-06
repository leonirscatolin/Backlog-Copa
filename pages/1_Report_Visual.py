# pages/1_Report_Visual.py (Nova Página)
import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime
from fpdf import FPDF

# --- Configuração da Página ---
st.set_page_config(layout="wide", page_title="Report Visual")

# --- FUNÇÕES DE PROCESSAMENTO (copiadas para cá) ---
def processar_dados_comparativos(df_atual, df_15dias):
    contagem_atual = df_atual.groupby('Atribuir a um grupo').size().reset_index(name='Atual')
    contagem_15dias = df_15dias.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
    df_comparativo = pd.merge(contagem_atual, contagem_15dias, on='Atribuir a um grupo', how='outer').fillna(0)
    df_comparativo['Diferença'] = df_comparativo['Atual'] - df_comparativo['15 Dias Atrás']
    df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']] = df_comparativo[['Atual', '15 Dias Atrás', 'Diferença']].astype(int)
    return df_comparativo

def categorizar_idade_vetorizado(dias_series):
    condicoes = [
        dias_series >= 30, (dias_series >= 21) & (dias_series <= 29),
        (dias_series >= 11) & (dias_series <= 20), (dias_series >= 6) & (dias_series <= 10),
        (dias_series >= 3) & (dias_series <= 5), (dias_series >= 0) & (dias_series <= 2)
    ]
    opcoes = ["30+ dias", "21 a 29 dias", "11 a 20 dias", "6 a 10 dias", "3 a 5 dias", "0 a 2 dias"]
    return np.select(condicoes, opcoes, default="Erro de Categoria")

def analisar_aging(df_atual):
    df = df_atual.copy()
    df['Data de criação'] = pd.to_datetime(df['Data de criação'], errors='coerce', dayfirst=True)
    df.dropna(subset=['Data de criação'], inplace=True)
    hoje = pd.to_datetime('today').normalize()
    data_criacao_normalizada = df['Data de criação'].dt.normalize()
    df['Dias em Aberto'] = (hoje - data_criacao_normalizada).dt.days + 1
    df['Faixa de Antiguidade'] = categorizar_idade_vetorizado(df['Dias em Aberto'])
    return df

# --- FUNÇÃO DE GERAÇÃO DE PDF ---
def criar_relatorio_pdf(total_chamados, fig_top_ofensores, fig_distribuicao):
    # Salva os gráficos como imagens temporárias
    fig_top_ofensores.write_image("temp_top_ofensores.png", scale=2)
    fig_distribuicao.write_image("temp_distribuicao.png", scale=2)

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)

    data_hoje = datetime.now().strftime("%d/%m/%Y")
    pdf.cell(0, 10, f"Report Visual de Backlog - {data_hoje}", 0, 1, "C")
    pdf.ln(10)

    # Adiciona o KPI
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Total de Chamados em Aberto: {total_chamados}", 0, 1, "L")
    pdf.ln(5)

    # Adiciona o gráfico de Top Ofensores
    pdf.cell(0, 10, "Top Ofensores", 0, 1, "L")
    pdf.image("temp_top_ofensores.png", x=10, y=pdf.get_y(), w=190)
    pdf.ln(85) # Pula o espaço da imagem

    # Adiciona o gráfico de Distribuição por Data
    pdf.cell(0, 10, "Distribuição por Data", 0, 1, "L")
    pdf.image("temp_distribuicao.png", x=10, y=pdf.get_y(), w=190)
    
    return pdf.output(dest='S').encode('latin-1')


# --- Corpo da Página ---
st.title("📄 Report Visual")

# Verifica se os dados foram carregados na página principal
if 'df_atual' not in st.session_state:
    st.warning("Por favor, carregue os arquivos CSV na página principal primeiro.")
    st.stop() # Interrompe a execução se não houver dados

# Recupera os dataframes da sessão
df_atual = st.session_state['df_atual']
df_15dias = st.session_state['df_15dias']

# Aplica filtros
df_atual_filtrado = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
df_aging = analisar_aging(df_atual_filtrado)

# --- GERAÇÃO DOS GRÁFICOS ---
total_chamados = len(df_aging)

# 1. KPI
st.metric(label="Total de Chamados em Aberto", value=total_chamados)
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    # 2. Gráfico de Top Ofensores
    st.subheader("Top Ofensores (Grupos com mais chamados)")
    top_ofensores = df_aging['Atribuir a um grupo'].value_counts().nlargest(10).sort_values(ascending=True)
    fig_top_ofensores = px.bar(
        top_ofensores,
        x=top_ofensores.values,
        y=top_ofensores.index,
        orientation='h',
        text=top_ofensores.values,
        labels={'x': 'Quantidade de Chamados', 'y': 'Grupo'}
    )
    fig_top_ofensores.update_traces(textposition='outside', marker_color='#375623')
    st.plotly_chart(fig_top_ofensores, use_container_width=True)

with col2:
    # 3. Gráfico de Distribuição por Data (Pizza)
    st.subheader("Distribuição por Data")
    dist_data = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
    dist_data.columns = ['Faixa de Antiguidade', 'Quantidade']
    fig_distribuicao = px.pie(
        dist_data,
        names='Faixa de Antiguidade',
        values='Quantidade',
        color_discrete_sequence=px.colors.sequential.Greens_r
    )
    st.plotly_chart(fig_distribuicao, use_container_width=True)

# --- BOTÃO DE DOWNLOAD DO PDF ---
st.markdown("---")
st.subheader("Exportar Relatório")

pdf_bytes = criar_relatorio_pdf(total_chamados, fig_top_ofensores, fig_distribuicao)
st.download_button(
    label="Gerar Relatório em PDF (A4)",
    data=pdf_bytes,
    file_name=f"report_visual_backlog_{datetime.now().strftime('%Y%m%d')}.pdf",
    mime="application/pdf"
)
