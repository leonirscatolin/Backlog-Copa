import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import base64
from datetime import datetime, date
from zoneinfo import ZoneInfo
from github import Github, Auth
from io import StringIO, BytesIO
import streamlit.components.v1 as components
from PIL import Image # Important for loading images

# --- Page Configuration ---
st.set_page_config(
    layout="wide",
    page_title="Backlog Copa Energia + Belago",
    page_icon="minilogo.png",
    initial_sidebar_state="collapsed"
)

# --- Functions ---
@st.cache_resource
def get_github_repo():
    try:
        auth = Auth.Token(st.secrets["GITHUB_TOKEN"])
        g = Github(auth=auth)
        return g.get_repo("leonirscatolin/dashboard-backlog")
    except Exception as e:
        st.error(f"Error connecting to repository: {e}")
        st.stop()

def update_github_file(_repo, file_path, file_content):
    commit_message = f"Data updated on {datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')}"
    try:
        contents = _repo.get_contents(file_path)
        _repo.update_file(contents.path, commit_message, file_content, contents.sha)
        st.sidebar.info(f"File '{file_path}' updated.")
    except Exception:
        _repo.create_file(file_path, commit_message, file_content)
        st.sidebar.info(f"File '{file_path}' created.")
    
@st.cache_data(ttl=300)
def read_github_file(_repo, file_path):
    try:
        content_file = _repo.get_contents(file_path)
        content = content_file.decoded_content.decode("utf-8")
        if not content.strip():
            return pd.DataFrame()
        return pd.read_csv(StringIO(content), delimiter=';', encoding='latin1')
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def read_github_text_file(_repo, file_path):
    try:
        content_file = _repo.get_contents(file_path)
        content = content_file.decoded_content.decode("utf-8")
        dates = {}
        for line in content.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                dates[key.strip()] = value.strip()
        return dates
    except Exception:
        return {}

def process_comparative_data(df_current, df_15_days):
    count_current = df_current.groupby('Atribuir a um grupo').size().reset_index(name='Atual')
    count_15_days = df_15_days.groupby('Atribuir a um grupo').size().reset_index(name='15 Dias Atrás')
    df_comparative = pd.merge(count_current, count_15_days, on='Atribuir a um grupo', how='outer').fillna(0)
    df_comparative['Diferença'] = df_comparative['Atual'] - df_comparative['15 Dias Atrás']
    df_comparative[['Atual', '15 Dias Atrás', 'Diferença']] = df_comparative[['Atual', '15 Dias Atrás', 'Diferença']].astype(int)
    return df_comparative

def categorize_age(days_series):
    conditions = [
        days_series >= 30,
        (days_series >= 21) & (days_series <= 29),
        (days_series >= 11) & (days_series <= 20),
        (days_series >= 6) & (days_series <= 10),
        (days_series >= 3) & (days_series <= 5),
        (days_series >= 0) & (days_series <= 2)
    ]
    options = ["30+ dias", "21-29 dias", "11-20 dias", "6-10 dias", "3-5 dias", "0-2 dias"]
    return np.select(conditions, options, default="Error Category")

def analyze_aging(df_current):
    df = df_current.copy()
    df['Data de criação'] = pd.to_datetime(df['Data de criação'], errors='coerce', dayfirst=True)
    df.dropna(subset=['Data de criação'], inplace=True)
    
    today = pd.to_datetime('today') 
    creation_date_normalized = df['Data de criação'].dt.normalize()
    
    df['Dias em Aberto'] = (today - creation_date_normalized).dt.days
    df['Faixa de Antiguidade'] = categorize_age(df['Dias em Aberto'])
    return df

def get_status(row):
    difference = row['Diferença']
    if difference > 0: return "High Demand"
    elif difference == 0: return "Stable / Attention"
    else: return "Backlog Reduction"

def process_uploaded_file(uploaded_file):
    if uploaded_file is None:
        return None
    try:
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
        else:
            content = uploaded_file.getvalue().decode('latin1')
            df = pd.read_csv(StringIO(content), delimiter=';', encoding='latin1')
        
        output = StringIO()
        df.to_csv(output, index=False, sep=';', encoding='latin1')
        return output.getvalue().encode('latin1')
    except Exception as e:
        st.sidebar.error(f"Error reading file {uploaded_file.name}: {e}")
        return None

# --- CSS Styling ---
st.html("""
    <style>
        #GithubIcon { visibility: hidden; }
        .metric-box {
            border: 1px solid #CCCCCC; padding: 10px; border-radius: 5px;
            text-align: center; box-shadow: 0px 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 10px;
        }
        a.metric-box {
            display: block; color: inherit; text-decoration: none !important;
        }
        a.metric-box:hover {
            background-color: #f0f2f6; text-decoration: none !important;
        }
        .metric-box span {
            display: block; width: 100%; text-decoration: none !important;
        }
        .metric-box .value {
            font-size: 2.5em; font-weight: bold; color: #375623;
        }
        .metric-box .label {
            font-size: 1em; color: #666666;
        }
    </style>
""")

# --- App Interface ---
try:
    logo_copa = Image.open("logo_sidebar.png")
    logo_belago = Image.open("logo_belago.png")
    col1, col2, col3 = st.columns([1, 4, 1])
    with col1: st.image(logo_copa, width=150)
    with col2: st.markdown("<h1 style='text-align: center;'>Backlog Copa Energia + Belago</h1>", unsafe_allow_html=True)
    with col3: st.image(logo_belago, width=150)
except FileNotFoundError:
    st.error("Logo files not found. Ensure 'logo_sidebar.png' and 'logo_belago.png' are in your repository.")

# --- Login & Upload Logic ---
st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha para atualizar dados:", type="password")
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "")
repo = get_github_repo()
if is_admin:
    st.sidebar.success("Acesso de administrador liberado.")
    st.sidebar.header("Carregar Novos Arquivos")
    
    file_types = ["csv", "xlsx"]
    uploaded_file_current = st.sidebar.file_uploader("1. Backlog ATUAL", type=file_types)
    uploaded_file_15_days = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS", type=file_types)
    uploaded_file_closed = st.sidebar.file_uploader("3. Chamados FECHADOS no dia (Opcional)", type=file_types)
    
    date_file_15_days = st.sidebar.date_input("Data de referência do arquivo de 15 DIAS", value=date.today())
    
    if st.sidebar.button("Salvar Novos Dados no Site"):
        if uploaded_file_current and uploaded_file_15_days:
            with st.spinner("Processando e salvando arquivos..."):
                content_current = process_uploaded_file(uploaded_file_current)
                content_15_days = process_uploaded_file(uploaded_file_15_days)
                content_closed = process_uploaded_file(uploaded_file_closed)

                if content_current is not None and content_15_days is not None:
                    update_github_file(repo, "dados_atuais.csv", content_current)
                    update_github_file(repo, "dados_15_dias.csv", content_15_days)
                    
                    if content_closed is not None:
                        update_github_file(repo, "dados_fechados.csv", content_closed)
                    else:
                        update_github_file(repo, "dados_fechados.csv", b"")

                    upload_date = date.today()
                    correct_time = datetime.now(ZoneInfo("America/Sao_Paulo"))
                    update_time = correct_time.strftime('%H:%M')
                    reference_content = (
                        f"data_atual:{upload_date.strftime('%d/%m/%Y')}\n"
                        f"data_15dias:{date_file_15_days.strftime('%d/%m/%Y')}\n"
                        f"hora_atualizacao:{update_time}"
                    )
                    update_github_file(repo, "datas_referencia.txt", reference_content.encode('utf-8'))

                    read_github_text_file.clear()
                    read_github_file.clear()
                    st.sidebar.success("Dados salvos com sucesso!")
        else:
            st.sidebar.warning("Carregue os arquivos obrigatórios (Atual e 15 Dias) para salvar.")
elif password:
    st.sidebar.error("Senha incorreta.")

# --- Main Display Logic ---
try:
    needs_scroll = "faixa" in st.query_params
    if "faixa" in st.query_params:
        faixa_from_url = st.query_params.get("faixa")
        valid_age_ranges = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
        if faixa_from_url in valid_age_ranges:
             st.session_state.faixa_selecionada = faixa_from_url
        st.query_params.clear()

    df_current = read_github_file(repo, "dados_atuais.csv")
    df_15_days = read_github_file(repo, "dados_15_dias.csv")
    df_closed = read_github_file(repo, "dados_fechados.csv")
    reference_data = read_github_text_file(repo, "datas_referencia.txt")
    current_date_str = reference_data.get('data_atual', 'N/A')
    date_15_days_str = reference_data.get('data_15dias', 'N/A')
    update_time_str = reference_data.get('hora_atualizacao', '')

    if df_current.empty or df_15_days.empty:
        st.warning("Ainda não há dados para exibir.")
    else:
        if not df_closed.empty and 'ID do ticket' in df_closed.columns:
            closed_ticket_ids = df_closed['ID do ticket'].dropna().unique()
            original_count = len(df_current)
            df_current = df_current[~df_current['ID do ticket'].isin(closed_ticket_ids)]
            num_closed = original_count - len(df_current)
            if num_closed > 0:
                st.info(f"ℹ️ {num_closed} chamados foram deduzidos da análise com base na lista de fechados do dia.")

        df_current_filtered = df_current[~df_current['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_15_days_filtered = df_15_days[~df_15_days['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
        df_aging = analyze_aging(df_current_filtered)
        
        tab1, tab2 = st.tabs(["Dashboard Completo", "Report Visual"])
        with tab1:
            st.info("""**Filtros e Regras Aplicadas:**\n- Grupos contendo 'RH' foram desconsiderados da análise.\n- A idade do chamado é o número de dias inteiros desde a criação.""")
            st.subheader("Análise de Antiguidade do Backlog Atual")

            time_text = f" (atualizado às {update_time_str})" if update_time_str else ""
            st.markdown(f"<p style='font-size: 0.9em; color: #666;'><i>Data de referência: {current_date_str}{time_text}</i></p>", unsafe_allow_html=True)

            if not df_aging.empty:
                total_tickets = len(df_aging)
                _, col_total, _ = st.columns([2, 1.5, 2])
                with col_total: st.markdown(f"""<div class="metric-box"><span class="value">{total_tickets}</span><span class="label">Total de Chamados</span></div>""", unsafe_allow_html=True)
                st.markdown("---")
                aging_counts = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                aging_counts.columns = ['Faixa de Antiguidade', 'Quantidade']
                age_ranges = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                all_ranges = pd.DataFrame({'Faixa de Antiguidade': age_ranges})
                aging_counts = pd.merge(all_ranges, aging_counts, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
                aging_counts['Faixa de Antiguidade'] = pd.Categorical(aging_counts['Faixa de Antiguidade'], categories=age_ranges, ordered=True)
                aging_counts = aging_counts.sort_values('Faixa de Antiguidade')
                if 'faixa_selecionada' not in st.session_state:
                    st.session_state.faixa_selecionada = "3-5 dias"
                cols = st.columns(len(age_ranges))
                for i, row in aging_counts.iterrows():
                    with cols[i]:
                        range_encoded = quote(row['Faixa de Antiguidade'])
                        card_html = f"""<a href="?faixa={range_encoded}" target="_self" class="metric-box"><span class="value">{row['Quantidade']}</span><span class="label">{row['Faixa de Antiguidade']}</span></a>"""
                        st.markdown(card_html, unsafe_allow_html=True)
            else:
                st.warning("Nenhum dado válido para a análise de antiguidade.")
            
            st.markdown(f"<h3>Comparativo de Backlog: Atual vs. 15 Dias Atrás <span style='font-size: 0.6em; color: #666; font-weight: normal;'>({date_15_days_str})</span></h3>", unsafe_allow_html=True)
            df_comparative = process_comparative_data(df_current_filtered.copy(), df_15_days_filtered.copy())
            df_comparative['Status'] = df_comparative.apply(get_status, axis=1)
            df_comparative.rename(columns={'Atribuir a um grupo': 'Grupo'}, inplace=True)
            df_comparative = df_comparative[['Grupo', '15 Dias Atrás', 'Atual', 'Diferença', 'Status']]
            st.dataframe(df_comparative.set_index('Grupo').style.map(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)

            if not df_aging.empty:
                st.markdown("---")
                st.subheader("Detalhar e Buscar Chamados")
                
                if needs_scroll:
                    js_code = """
                        <script>
                            setTimeout(function() {
                                const element = window.parent.document.getElementById('detalhar-e-buscar-chamados');
                                if (element) {
                                    element.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                }
                            }, 500);
                        </script>
                    """
                    components.html(js_code, height=0)

                st.selectbox("Selecione uma faixa de idade para ver os detalhes (ou clique em um card acima):", options=age_ranges, key='faixa_selecionada')
                
                current_range = st.session_state.faixa_selecionada
                filtered_df = df_aging[df_aging['Faixa de Antiguidade'] == current_range].copy()
                
                if not filtered_df.empty:
                    filtered_df['Data de criação'] = filtered_df['Data de criação'].dt.strftime('%d/%m/%Y')
                    display_cols = ['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto', 'Data de criação']
                    st.data_editor(filtered_df[display_cols], use_container_width=True, hide_index=True, disabled=True)
                else:
                    st.info("Não há chamados nesta categoria.")

                st.subheader("Buscar Chamados por Grupo")
                
                group_list = sorted(df_aging['Atribuir a um grupo'].dropna().unique())
                selected_group = st.selectbox("Busca de chamados por grupo:", options=group_list)
                
                if selected_group:
                    search_results = df_aging[df_aging['Atribuir a um grupo'] == selected_group].copy()
                    search_results['Data de criação'] = search_results['Data de criação'].dt.strftime('%d/%m/%Y')
                    st.write(f"Encontrados {len(search_results)} chamados para o grupo '{selected_group}':")
                    search_display_cols = ['ID do ticket', 'Descrição', 'Dias em Aberto', 'Data de criação']
                    st.data_editor(search_results[search_display_cols], use_container_width=True, hide_index=True, disabled=True)

        with tab2:
            st.subheader("Resumo do Backlog Atual")
            if not df_aging.empty:
                total_tickets = len(df_aging)
                _, col_total_tab2, _ = st.columns([2, 1.5, 2])
                with col_total_tab2: st.markdown( f"""<div class="metric-box"><span class="value">{total_tickets}</span><span class="label">Total de Chamados</span></div>""", unsafe_allow_html=True )
                st.markdown("---")
                aging_counts_tab2 = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                aging_counts_tab2.columns = ['Faixa de Antiguidade', 'Quantidade']
                age_ranges_tab2 = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
                all_ranges_tab2 = pd.DataFrame({'Faixa de Antiguidade': age_ranges_tab2})
                aging_counts_tab2 = pd.merge(all_ranges_tab2, aging_counts_tab2, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
                aging_counts_tab2['Faixa de Antiguidade'] = pd.Categorical(aging_counts_tab2['Faixa de Antiguidade'], categories=age_ranges_tab2, ordered=True)
                aging_counts_tab2 = aging_counts_tab2.sort_values('Faixa de Antiguidade')
                cols_tab2 = st.columns(len(age_ranges_tab2))
                for i, row in aging_counts_tab2.iterrows():
                    with cols_tab2[i]: st.markdown( f"""<div class="metric-box"><span class="value">{row['Quantidade']}</span><span class="label">{row['Faixa de Antiguidade']}</span></div>""", unsafe_allow_html=True )
                st.markdown("---")
                st.subheader("Ofensores (Todos os Grupos)")
                top_offenders = df_aging['Atribuir a um grupo'].value_counts().sort_values(ascending=True)
                fig_top_offenders = px.bar(top_offenders, x=top_offenders.values, y=top_offenders.index, orientation='h', text=top_offenders.values, labels={'x': 'Qtd. Chamados', 'y': 'Grupo'})
                fig_top_offenders.update_traces(textposition='outside', marker_color='#375623')
                fig_top_offenders.update_layout(height=max(400, len(top_offenders) * 25))
                st.plotly_chart(fig_top_offenders, use_container_width=True)
            else:
                st.warning("Nenhum dado para gerar o report visual.")

except Exception as e:
    st.error(f"Ocorreu um erro ao carregar os dados: {e}")
