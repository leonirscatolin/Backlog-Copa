# ... (código anterior) ...

logo_copa_b64 = get_image_as_base64("logo_sidebar.png")
logo_belago_b64 = get_image_as_base64("logo_belago.png")
if logo_copa_b64 and logo_belago_b64:
    st.markdown(f"""<div style="display: flex; justify-content: space-between; align-items: center;"><img src="data:image/png;base64,{logo_copa_b64}" width="150"><h1 style='text-align: center; margin: 0;'>Backlog Copa Energia + Belago</h1><img src="data:image/png;base64,{logo_belago_b64}" width="150"></div>""", unsafe_allow_html=True)
else:
    # Se os logos não forem encontrados, continua mas avisa
    st.warning("Arquivos de logo ('logo_sidebar.png', 'logo_belago.png') não encontrados.")
    st.markdown("<h1 style='text-align: center; margin: 0;'>Backlog Copa Energia + Belago</h1>", unsafe_allow_html=True)


# ==========================================================
# ||           INICIALIZAÇÃO DO REPOSITÓRIO GITHUB        ||
# ==========================================================
try:
    repo = get_github_repo()
    # Verifica se a função retornou um objeto válido
    if repo is None:
         st.error("Falha ao obter o objeto do repositório do GitHub. A função get_github_repo retornou None.")
         st.stop()
    st.session_state.repo = repo # Armazena no session_state logo após definir
except Exception as e:
     st.error(f"Erro CRÍTICO durante a inicialização do repositório GitHub: {e}")
     st.stop()
# ==========================================================


st.sidebar.header("Área do Administrador")
password = st.sidebar.text_input("Senha para atualizar dados:", type="password")
is_admin = password == st.secrets.get("ADMIN_PASSWORD", "")

if is_admin:
    # ... (código da sidebar do admin permanece o mesmo) ...
    st.sidebar.success("Acesso de administrador liberado.")
    st.sidebar.subheader("Atualização Completa")
    uploaded_file_atual = st.sidebar.file_uploader("1. Backlog ATUAL", type=["csv", "xlsx"], key="uploader_atual")
    uploaded_file_15dias = st.sidebar.file_uploader("2. Backlog de 15 DIAS ATRÁS", type=["csv", "xlsx"], key="uploader_15dias")
    if st.sidebar.button("Salvar Novos Dados no Site"):
        if uploaded_file_atual and uploaded_file_15dias:
            with st.spinner("Processando e salvando atualização completa..."):
                now_sao_paulo = datetime.now(ZoneInfo('America/Sao_Paulo'))
                commit_msg = f"Dados atualizados em {now_sao_paulo.strftime('%d/%m/%Y %H:%M')}"
                content_atual = process_uploaded_file(uploaded_file_atual)
                content_15dias = process_uploaded_file(uploaded_file_15dias)
                if content_atual is not None and content_15dias is not None:
                    try:
                        # Usa st.session_state.repo para consistência
                        update_github_file(st.session_state.repo, "dados_atuais.csv", content_atual, commit_msg)
                        update_github_file(st.session_state.repo, "dados_15_dias.csv", content_15dias, commit_msg)
                        today_str = now_sao_paulo.strftime('%Y-%m-%d')
                        snapshot_path = f"snapshots/backlog_{today_str}.csv"
                        update_github_file(st.session_state.repo, snapshot_path, content_atual, f"Snapshot de {today_str}")
                        data_do_upload = now_sao_paulo.date()
                        data_arquivo_15dias = data_do_upload - timedelta(days=15)
                        hora_atualizacao = now_sao_paulo.strftime('%H:%M')
                        datas_referencia_content = (f"data_atual:{data_do_upload.strftime('%d/%m/%Y')}\n"
                                                    f"data_15dias:{data_arquivo_15dias.strftime('%d/%m/%Y')}\n"
                                                    f"hora_atualizacao:{hora_atualizacao}")
                        update_github_file(st.session_state.repo, "datas_referencia.txt", datas_referencia_content.encode('utf-8'), commit_msg)
                        
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        st.sidebar.success("Arquivos salvos! Forçando recarregamento...")
                        st.rerun()
                    # Captura exceções específicas do update_github_file ou gerais
                    except GithubException as ghe:
                         st.sidebar.error(f"Erro GitHub durante a atualização completa ({ghe.status}): {ghe.data.get('message', 'Erro desconhecido')}")
                    except Exception as e:
                        st.sidebar.error(f"Erro durante a atualização completa: {e}")

        else:
            st.sidebar.warning("Para a atualização completa, carregue os arquivos ATUAL e de 15 DIAS.")
    st.sidebar.markdown("---")
    st.sidebar.subheader("Atualização Rápida")
    uploaded_file_fechados = st.sidebar.file_uploader("Apenas Chamados FECHADOS no dia", type=["csv", "xlsx"], key="uploader_fechados")
    if st.sidebar.button("Salvar Apenas Chamados Fechados"):
        if uploaded_file_fechados:
            with st.spinner("Salvando arquivo de chamados fechados..."):
                now_sao_paulo = datetime.now(ZoneInfo('America/Sao_Paulo'))
                commit_msg = f"Atualizando chamados fechados em {now_sao_paulo.strftime('%d/%m/%Y %H:%M')}"
                content_fechados = process_uploaded_file(uploaded_file_fechados)
                if content_fechados is not None:
                    try:
                        # Usa st.session_state.repo
                        update_github_file(st.session_state.repo, "dados_fechados.csv", content_fechados, commit_msg)

                        # Usa st.session_state.repo aqui também
                        datas_existentes = read_github_text_file(st.session_state.repo, "datas_referencia.txt")
                        data_atual_existente = datas_existentes.get('data_atual', 'N/A')
                        data_15dias_existente = datas_existentes.get('data_15dias', 'N/A')
                        hora_atualizacao_nova = now_sao_paulo.strftime('%H:%M')

                        datas_referencia_content_novo = (f"data_atual:{data_atual_existente}\n"
                                                       f"data_15dias:{data_15dias_existente}\n"
                                                       f"hora_atualizacao:{hora_atualizacao_nova}")
                        update_github_file(st.session_state.repo, "datas_referencia.txt", datas_referencia_content_novo.encode('utf-8'), commit_msg)

                        st.cache_data.clear()
                        st.cache_resource.clear()
                        st.sidebar.success("Arquivo de fechados salvo e hora atualizada! Recarregando...")
                        st.rerun()
                    # Captura exceções específicas do update_github_file ou gerais
                    except GithubException as ghe:
                         st.sidebar.error(f"Erro GitHub durante a atualização rápida ({ghe.status}): {ghe.data.get('message', 'Erro desconhecido')}")
                    except Exception as e:
                        st.sidebar.error(f"Erro durante a atualização rápida: {e}")
        else:
            st.sidebar.warning("Por favor, carregue o arquivo de chamados fechados para salvar.")
elif password:
    st.sidebar.error("Senha incorreta.")


# --- Bloco Principal ---
# Agora usa st.session_state.repo, que foi garantido na inicialização
# Usa um bloco try/except abrangente para pegar erros gerais de processamento
try:
    # Garante que repo existe no session_state antes de prosseguir
    if 'repo' not in st.session_state or st.session_state.repo is None:
         st.error("Objeto do repositório GitHub não encontrado no estado da sessão. A inicialização falhou.")
         st.stop()
         
    # Usa st.session_state.repo daqui em diante
    _repo = st.session_state.repo

    # Carrega estado inicial (contatos, observações) usando _repo
    if 'contacted_tickets' not in st.session_state:
        # ... (código para carregar contacted_tickets usando _repo) ...
        try:
            file_content_obj = _repo.get_contents("contacted_tickets.json")
            file_content_str = file_content_obj.decoded_content.decode("utf-8")
            st.session_state.contacted_tickets = set(json.loads(file_content_str)) if file_content_str.strip() else set()
        except GithubException as e:
            if e.status == 404: st.session_state.contacted_tickets = set()
            else: st.error(f"Erro GitHub ao carregar 'contacted_tickets.json' ({e.status}): {e.data.get('message', 'Erro desconhecido')}"); st.session_state.contacted_tickets = set()
        except json.JSONDecodeError:
             st.warning("Arquivo 'contacted_tickets.json' corrompido ou vazio. Iniciando lista vazia.")
             st.session_state.contacted_tickets = set()

    if 'observations' not in st.session_state:
        # Passa _repo para a função
        st.session_state.observations = read_github_json_dict(_repo, "ticket_observations.json")

    # ... (Trata parâmetros da URL - sem alterações) ...
    needs_scroll = "scroll" in st.query_params
    if "faixa" in st.query_params:
        faixa_from_url = st.query_params.get("faixa")
        ordem_faixas_validas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
        if faixa_from_url in ordem_faixas_validas:
                st.session_state.faixa_selecionada = faixa_from_url
    if "scroll" in st.query_params or "faixa" in st.query_params:
        st.query_params.clear() 

    # --- Carregamento e Pré-processamento dos Dados (usando _repo) ---
    df_atual = read_github_file(_repo, "dados_atuais.csv")
    df_15dias = read_github_file(_repo, "dados_15_dias.csv")
    df_fechados_raw = read_github_file(_repo, "dados_fechados.csv")
    datas_referencia = read_github_text_file(_repo, "datas_referencia.txt")
    data_atual_str = datas_referencia.get('data_atual', 'N/A')
    data_15dias_str = datas_referencia.get('data_15dias', 'N/A')
    hora_atualizacao_str = datas_referencia.get('hora_atualizacao', '')

    # ... (Restante do pré-processamento e lógica das abas permanece o mesmo,
    #      mas garanta que todas as chamadas de função que precisam do repo
    #      recebam `_repo` ou usem `st.session_state.repo`) ...

    # Exemplo: Dentro das abas, ao chamar funções cacheadas que usam o repo
    # with tab3:
    #    df_evolucao_tab3 = carregar_dados_evolucao(_repo, ...)
    # with tab4:
    #    df_hist = carregar_evolucao_aging(_repo, ...)
    #    data_comparacao_encontrada, _ = find_closest_snapshot_before(_repo, ...)

    # --- Aplica filtros e processa dados ---
    if df_atual.empty:
        st.warning("Arquivo 'dados_atuais.csv' não encontrado ou vazio.")
        st.stop()

    if 'Atribuir a um grupo' in df_atual.columns:
        df_atual = df_atual[~df_atual['Atribuir a um grupo'].isin(grupos_excluidos)].copy()
    else:
        st.error("Coluna 'Atribuir a um grupo' não encontrada em dados_atuais.csv.")
        st.stop()

    if not df_15dias.empty and 'Atribuir a um grupo' in df_15dias.columns:
        df_15dias_filtrado_ocultos = df_15dias[~df_15dias['Atribuir a um grupo'].isin(grupos_excluidos)].copy()
    else:
        df_15dias_filtrado_ocultos = pd.DataFrame()

    id_col_atual = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_atual.columns), None)
    if id_col_atual:
        df_atual[id_col_atual] = df_atual[id_col_atual].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        if id_col_atual != 'ID do ticket': 
            df_atual.rename(columns={id_col_atual: 'ID do ticket'}, inplace=True)
        id_col_atual = 'ID do ticket' 
    else:
        st.error("Coluna de ID ('ID do ticket', 'ID do Ticket', 'ID') não encontrada em dados_atuais.csv.")
        st.stop() 

    closed_ticket_ids = np.array([]) 
    if not df_fechados_raw.empty:
        id_col_fechados = next((col for col in ['ID do ticket', 'ID do Ticket', 'ID'] if col in df_fechados_raw.columns), None)
        if id_col_fechados:
            ids_fechados_series = df_fechados_raw[id_col_fechados].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().dropna()
            closed_ticket_ids = ids_fechados_series.unique()
        else:
             st.warning("Arquivo 'dados_fechados.csv' carregado, mas coluna de ID não encontrada.")

    df_atual_filtrado_rh = df_atual[~df_atual['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]

    if not df_15dias_filtrado_ocultos.empty:
        df_15dias_filtrado = df_15dias_filtrado_ocultos[~df_15dias_filtrado_ocultos['Atribuir a um grupo'].str.contains('RH', case=False, na=False)]
    else:
        df_15dias_filtrado = pd.DataFrame() 

    df_todos_com_aging = analisar_aging(df_atual_filtrado_rh.copy()) 

    if df_todos_com_aging.empty:
         st.error("A análise de aging não retornou nenhum dado válido para os dados atuais.")
         st.stop()

    df_encerrados_filtrado = df_todos_com_aging[df_todos_com_aging[id_col_atual].isin(closed_ticket_ids)]
    df_aging = df_todos_com_aging[~df_todos_com_aging[id_col_atual].isin(closed_ticket_ids)]
    
    # --- Fim do Pré-processamento ---

    tab1, tab2, tab3, tab4 = st.tabs(["Dashboard Completo", "Report Visual", "Evolução Semanal", "Evolução Aging"])
    
    # --- Tab 1 ---
    with tab1:
        # ... (código da tab 1) ...
        info_messages = ["**Filtros e Regras Aplicadas:**", 
                         f"- Grupos ocultos ({', '.join(grupos_excluidos)}) e grupos contendo 'RH' foram desconsiderados da análise.", 
                         "- A contagem de dias do chamado desconsidera o dia da sua abertura (prazo -1 dia)."]
        if closed_ticket_ids.size > 0: 
            info_messages.append(f"- **{len(df_encerrados_filtrado)} chamados fechados no dia** (exceto RH e ocultos) foram deduzidos das contagens principais e movidos para a tabela de encerrados.")
        st.info("\n".join(info_messages))
        
        st.subheader("Análise de Antiguidade do Backlog Atual")
        texto_hora = f" (atualizado às {hora_atualizacao_str})" if hora_atualizacao_str else ""
        st.markdown(f"<p style='font-size: 0.9em; color: #666;'><i>Data de referência: {data_atual_str}{texto_hora}</i></p>", unsafe_allow_html=True)
        
        if not df_aging.empty:
            total_chamados = len(df_aging)
            total_fechados = len(df_encerrados_filtrado)
            col_spacer1, col_total, col_fechados, col_spacer2 = st.columns([1, 1.5, 1.5, 1])
            with col_total:
                st.markdown(f"""<div class="metric-box"><span class="label">Total de Chamados Abertos</span><span class="value">{total_chamados}</span></div>""", unsafe_allow_html=True)
            with col_fechados:
                st.markdown(f"""<div class="metric-box"><span class="label">Chamados Fechados no Dia</span><span class="value">{total_fechados}</span></div>""", unsafe_allow_html=True)

            st.markdown("---")
            aging_counts = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
            aging_counts.columns = ['Faixa de Antiguidade', 'Quantidade']
            ordem_faixas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            todas_as_faixas = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
            aging_counts = pd.merge(todas_as_faixas, aging_counts, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
            aging_counts['Faixa de Antiguidade'] = pd.Categorical(aging_counts['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
            aging_counts = aging_counts.sort_values('Faixa de Antiguidade')
            if 'faixa_selecionada' not in st.session_state:
                st.session_state.faixa_selecionada = "0-2 dias" 
            
            if st.session_state.faixa_selecionada not in ordem_faixas:
                 st.session_state.faixa_selecionada = "0-2 dias" 

            cols = st.columns(len(ordem_faixas))
            for i, row in aging_counts.iterrows():
                with cols[i]:
                    faixa_encoded = quote(row['Faixa de Antiguidade'])
                    card_html = f"""<a href="?faixa={faixa_encoded}&scroll=true" target="_self" class="metric-box"><span class="label">{row['Faixa de Antiguidade']}</span><span class="value">{row['Quantidade']}</span></a>"""
                    st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning("Nenhum chamado aberto encontrado após aplicar os filtros.")

        st.markdown(f"<h3>Comparativo de Backlog: Atual vs. 15 Dias Atrás <span style='font-size: 0.6em; color: #666; font-weight: normal;'>({data_15dias_str if not df_15dias_filtrado.empty else 'Dados Indisponíveis'})</span></h3>", unsafe_allow_html=True)
        if not df_15dias_filtrado.empty:
            df_comparativo = processar_dados_comparativos(df_aging.copy(), df_15dias_filtrado.copy()) 
            if not df_comparativo.empty: 
                 df_comparativo['Status'] = df_comparativo.apply(get_status, axis=1)
                 df_comparativo = df_comparativo.rename(columns={'Atribuir a um grupo': 'Grupo'}) 
                 df_comparativo = df_comparativo[['Grupo', '15 Dias Atrás', 'Atual', 'Diferença', 'Status']]
                 st.dataframe(df_comparativo.set_index('Grupo').style.map(lambda val: 'background-color: #ffcccc' if val > 0 else ('background-color: #ccffcc' if val < 0 else 'background-color: white'), subset=['Diferença']), use_container_width=True)
            else:
                 st.info("Nenhum dado comum encontrado para comparação entre os períodos.")
        else:
             st.warning("Não foi possível carregar ou processar os dados de 15 dias atrás para comparação.")
        
        st.markdown("---")

        st.markdown(f"<h3>Chamados Encerrados no Dia <span style='font-size: 0.6em; color: #666; font-weight: normal;'>({data_atual_str})</span></h3>", unsafe_allow_html=True)
        if not closed_ticket_ids.size > 0: 
             st.info("O arquivo de chamados encerrados do dia ('dados_fechados.csv') ainda não foi carregado.")
        elif not df_encerrados_filtrado.empty:
            colunas_fechados = ['ID do ticket', 'Descrição', 'Atribuir a um grupo', 'Dias em Aberto']
            colunas_existentes_fechados = [col for col in colunas_fechados if col in df_encerrados_filtrado.columns]
            st.data_editor(
                df_encerrados_filtrado[colunas_existentes_fechados], 
                hide_index=True, disabled=True, use_container_width=True,
                key="editor_fechados" 
            )
        else:
             st.info("Nenhum chamado encerrado hoje pertence aos grupos analisados.") 

        if not df_aging.empty:
            st.markdown("---")
            st.subheader("Detalhar e Buscar Chamados Abertos", anchor="detalhar-e-buscar-chamados-abertos") 
            st.info('Marque "Contato" se já falou com o usuário e a solicitação continua pendente. Use "Observações" para anotações.')

            if 'scroll_to_details' not in st.session_state:
                st.session_state.scroll_to_details = False
            if needs_scroll or st.session_state.get('scroll_to_details', False):
                js_code = """<script> setTimeout(() => { const element = window.parent.document.getElementById('detalhar-e-buscar-chamados-abertos'); if (element) { element.scrollIntoView({ behavior: 'smooth', block: 'start' }); } }, 250); </script>"""
                components.html(js_code, height=0)
                st.session_state.scroll_to_details = False 

            st.selectbox("Selecione uma faixa de idade para ver os detalhes (ou clique em um card acima):", 
                         options=ordem_faixas, key='faixa_selecionada') 
            
            faixa_atual = st.session_state.faixa_selecionada
            filtered_df = df_aging[df_aging['Faixa de Antiguidade'] == faixa_atual].copy()
            
            if not filtered_df.empty:
                def highlight_row(row):
                    return ['background-color: #fff8c4'] * len(row) if row.get('Contato', False) else [''] * len(row)

                filtered_df['Contato'] = filtered_df['ID do ticket'].apply(lambda id: str(id) in st.session_state.contacted_tickets)
                filtered_df['Observações'] = filtered_df['ID do ticket'].apply(lambda id: st.session_state.observations.get(str(id), ''))

                st.session_state.last_filtered_df = filtered_df.reset_index(drop=True) 

                colunas_para_exibir_renomeadas = {
                    'Contato': 'Contato', 'ID do ticket': 'ID do ticket', 'Descrição': 'Descrição',
                    'Atribuir a um grupo': 'Grupo Atribuído', 'Dias em Aberto': 'Dias em Aberto',
                    'Data de criação': 'Data de criação', 'Observações': 'Observações'
                }
                colunas_existentes = [col for col in colunas_para_exibir_renomeadas if col in filtered_df.columns]
                colunas_renomeadas_existentes = [colunas_para_exibir_renomeadas[col] for col in colunas_existentes]
                colunas_editaveis = ['Contato', 'Observações'] 
                colunas_desabilitadas = [colunas_para_exibir_renomeadas[c] for c in colunas_existentes if c not in colunas_editaveis]


                st.data_editor(
                    st.session_state.last_filtered_df.rename(columns=colunas_para_exibir_renomeadas)[colunas_renomeadas_existentes].style.apply(highlight_row, axis=1),
                    use_container_width=True, hide_index=True, disabled=colunas_desabilitadas, 
                    key='ticket_editor', on_change=sync_ticket_data
                )
            else:
                st.info(f"Não há chamados abertos na faixa '{faixa_atual}'.")
            
            st.subheader("Buscar Chamados Abertos por Grupo")
            if 'Atribuir a um grupo' in df_aging.columns:
                 lista_grupos = sorted(df_aging['Atribuir a um grupo'].dropna().unique())
                 if lista_grupos:
                      grupo_selecionado = st.selectbox("Selecione um grupo:", options=lista_grupos, key="busca_grupo")
                      if grupo_selecionado:
                           resultados_busca = df_aging[df_aging['Atribuir a um grupo'] == grupo_selecionado].copy()
                           
                           date_col_name_busca = next((col for col in ['Data de criação', 'Data de Criacao'] if col in resultados_busca.columns), None)
                           if date_col_name_busca:
                                resultados_busca[date_col_name_busca] = pd.to_datetime(resultados_busca[date_col_name_busca]).dt.strftime('%d/%m/%Y')

                           st.write(f"Encontrados {len(resultados_busca)} chamados abertos para o grupo '{grupo_selecionado}':")
                           
                           colunas_para_exibir_busca = ['ID do ticket', 'Descrição', 'Dias em Aberto', date_col_name_busca]
                           colunas_existentes_busca = [col for col in colunas_para_exibir_busca if col in resultados_busca.columns and col is not None] 
                           
                           st.data_editor(
                                resultados_busca[colunas_existentes_busca], 
                                use_container_width=True, hide_index=True, disabled=True,
                                key="editor_busca" 
                           )
                 else:
                      st.info("Nenhum grupo encontrado nos chamados abertos para seleção.")
            else:
                 st.warning("Coluna 'Atribuir a um grupo' não encontrada para busca.")


    # --- Tab 2 ---
    with tab2:
        # ... (código da tab 2) ...
        st.subheader("Resumo do Backlog Atual")
        if not df_aging.empty:
            total_chamados = len(df_aging)
            _, col_total_tab2, _ = st.columns([2, 1.5, 2])
            with col_total_tab2: st.markdown( f"""<div class="metric-box"><span class="label">Total de Chamados</span><span class="value">{total_chamados}</span></div>""", unsafe_allow_html=True )
            st.markdown("---")
            aging_counts_tab2 = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
            aging_counts_tab2.columns = ['Faixa de Antiguidade', 'Quantidade']
            ordem_faixas = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            todas_as_faixas_tab2 = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas})
            aging_counts_tab2 = pd.merge(todas_as_faixas_tab2, aging_counts_tab2, on='Faixa de Antiguidade', how='left').fillna(0).astype({'Quantidade': int})
            aging_counts_tab2['Faixa de Antiguidade'] = pd.Categorical(aging_counts_tab2['Faixa de Antiguidade'], categories=ordem_faixas, ordered=True)
            aging_counts_tab2 = aging_counts_tab2.sort_values('Faixa de Antiguidade')
            cols_tab2 = st.columns(len(ordem_faixas))
            for i, row in aging_counts_tab2.iterrows():
                with cols_tab2[i]: st.markdown( f"""<div class="metric-box"><span class="label">{row['Faixa de Antiguidade']}</span><span class="value">{row['Quantidade']}</span></div>""", unsafe_allow_html=True )
            st.markdown("---")
            st.subheader("Distribuição do Backlog por Grupo")
            orientation_choice = st.radio( "Orientação do Gráfico:", ["Vertical", "Horizontal"], index=0, horizontal=True )
            
            if 'Atribuir a um grupo' in df_aging.columns and 'Faixa de Antiguidade' in df_aging.columns:
                 chart_data = df_aging.groupby(['Atribuir a um grupo', 'Faixa de Antiguidade']).size().reset_index(name='Quantidade')
                 group_totals = chart_data.groupby('Atribuir a um grupo')['Quantidade'].sum().sort_values(ascending=False)
                 
                 if not group_totals.empty:
                      new_labels_map = {group: f"{group} ({total})" for group, total in group_totals.items()}
                      chart_data['Atribuir a um grupo'] = chart_data['Atribuir a um grupo'].map(new_labels_map)
                      sorted_new_labels = [new_labels_map[group] for group in group_totals.index]
                      def lighten_color(hex_color, amount=0.2):
                          try:
                              hex_color = hex_color.lstrip('#')
                              h, l, s = colorsys.rgb_to_hls(*[int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4)])
                              new_l = l + (1 - l) * amount
                              r, g, b = colorsys.hls_to_rgb(h, new_l, s)
                              return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                          except Exception: return hex_color
                      base_color = "#375623"
                      palette = [ lighten_color(base_color, 0.85), lighten_color(base_color, 0.70), lighten_color(base_color, 0.55), lighten_color(base_color, 0.40), lighten_color(base_color, 0.20), base_color ]
                      color_map = {faixa: color for faixa, color in zip(ordem_faixas, palette)}
                      
                      if orientation_choice == 'Horizontal':
                          num_groups = len(group_totals)
                          dynamic_height = max(500, num_groups * 30) 
                          fig_stacked_bar = px.bar( chart_data, x='Quantidade', y='Atribuir a um grupo', orientation='h', color='Faixa de Antiguidade', title="Composição da Idade do Backlog por Grupo", labels={'Quantidade': 'Qtd. de Chamados', 'Atribuir a um grupo': ''}, category_orders={'Atribuir a um grupo': sorted_new_labels, 'Faixa de Antiguidade': ordem_faixas}, color_discrete_map=color_map, text_auto=True )
                          fig_stacked_bar.update_traces(textangle=0, textfont_size=12)
                          fig_stacked_bar.update_layout(height=dynamic_height, legend_title_text='Antiguidade', yaxis={'categoryorder':'array', 'categoryarray':sorted_new_labels[::-1]}) 
                      else: 
                          fig_stacked_bar = px.bar( chart_data, x='Atribuir a um grupo', y='Quantidade', color='Faixa de Antiguidade', title="Composição da Idade do Backlog por Grupo", labels={'Quantidade': 'Qtd. de Chamados', 'Atribuir a um grupo': 'Grupo'}, category_orders={'Atribuir a um grupo': sorted_new_labels, 'Faixa de Antiguidade': ordem_faixas}, color_discrete_map=color_map, text_auto=True )
                          fig_stacked_bar.update_traces(textangle=0, textfont_size=12)
                          fig_stacked_bar.update_layout(height=600, xaxis_title=None, xaxis_tickangle=-45, legend_title_text='Antiguidade')
                      
                      st.plotly_chart(fig_stacked_bar, use_container_width=True)
                 else:
                      st.info("Nenhum grupo encontrado para gerar o gráfico de distribuição.")
            else:
                 st.warning("Colunas necessárias ('Atribuir a um grupo', 'Faixa de Antiguidade') não encontradas para gerar o gráfico.")
        else:
            st.warning("Nenhum dado de aging disponível para gerar o report visual.")


    # --- Tab 3 ---
    with tab3:
        # ... (código da tab 3) ...
        st.subheader("Evolução do Backlog")
        dias_evolucao = st.slider("Ver evolução dos últimos dias:", min_value=7, max_value=30, value=7, key="slider_evolucao")

        # Passa _repo
        df_evolucao_tab3 = carregar_dados_evolucao(_repo, dias_para_analisar=dias_evolucao)

        if not df_evolucao_tab3.empty:
            df_evolucao_tab3['Data'] = pd.to_datetime(df_evolucao_tab3['Data'])
            df_evolucao_semana = df_evolucao_tab3[df_evolucao_tab3['Data'].dt.dayofweek < 5].copy()

            if not df_evolucao_semana.empty:
                st.info("Esta visualização considera apenas os dados de snapshots de dias de semana e já aplica os filtros de grupos ocultos e RH.")

                df_total_diario = df_evolucao_semana.groupby('Data')['Total Chamados'].sum().reset_index()
                df_total_diario = df_total_diario.sort_values('Data')
                df_total_diario['Data (Eixo)'] = df_total_diario['Data'].dt.strftime('%d/%m')
                ordem_datas_total = df_total_diario['Data (Eixo)'].tolist()

                fig_total_evolucao = px.area(
                    df_total_diario, x='Data (Eixo)', y='Total Chamados',
                    title='Evolução do Total Geral de Chamados Abertos (Apenas Dias de Semana)',
                    markers=True, labels={"Data (Eixo)": "Data", "Total Chamados": "Total Geral de Chamados"},
                    category_orders={'Data (Eixo)': ordem_datas_total}
                )
                fig_total_evolucao.update_layout(height=400)
                st.plotly_chart(fig_total_evolucao, use_container_width=True)

                st.markdown("---")

                st.info("Clique na legenda para filtrar grupos. Clique duplo para isolar um grupo.")
                df_evolucao_semana_sorted = df_evolucao_semana.sort_values('Data')
                df_evolucao_semana_sorted['Data (Eixo)'] = df_evolucao_semana_sorted['Data'].dt.strftime('%d/%m')
                ordem_datas_grupo = df_evolucao_semana_sorted['Data (Eixo)'].unique().tolist()
                df_filtrado_display = df_evolucao_semana_sorted.rename(columns={'Atribuir a um grupo': 'Grupo Atribuído'})

                fig_evolucao_grupo = px.line(
                    df_filtrado_display, x='Data (Eixo)', y='Total Chamados', color='Grupo Atribuído',
                    title='Evolução por Grupo (Apenas Dias de Semana)', markers=True,
                    labels={ "Data (Eixo)": "Data", "Total Chamados": "Nº de Chamados", "Grupo Atribuído": "Grupo" },
                    category_orders={'Data (Eixo)': ordem_datas_grupo}
                )
                fig_evolucao_grupo.update_layout(height=600)
                st.plotly_chart(fig_evolucao_grupo, use_container_width=True)

            else:
                st.info("Não há dados históricos suficientes considerando apenas dias de semana.")
        else:
            st.info("Não foi possível carregar dados históricos para a evolução.")


    # --- Tab 4 ---
    with tab4:
        # ... (código da tab 4) ...
        st.subheader("Evolução do Aging do Backlog")
        st.info("Esta aba compara a 'foto' do aging de hoje com a 'foto' de dias anteriores, usando a mesma data de referência (hoje) para calcular a idade em ambos os momentos.")

        try:
            # Passa _repo
            df_hist = carregar_evolucao_aging(_repo, dias_para_analisar=90)

            ordem_faixas_scaffold = ["0-2 dias", "3-5 dias", "6-10 dias", "11-20 dias", "21-29 dias", "30+ dias"]
            hoje_data = None
            hoje_counts_df = pd.DataFrame() 

            if 'df_aging' in locals() and not df_aging.empty and data_atual_str != 'N/A':
                try:
                    hoje_data = pd.to_datetime(datetime.strptime(data_atual_str, "%d/%m/%Y").date())
                    hoje_counts_raw = df_aging['Faixa de Antiguidade'].value_counts().reset_index()
                    hoje_counts_raw.columns = ['Faixa de Antiguidade', 'total']
                    df_todas_faixas_hoje = pd.DataFrame({'Faixa de Antiguidade': ordem_faixas_scaffold})
                    hoje_counts_df = pd.merge(
                        df_todas_faixas_hoje, hoje_counts_raw,
                        on='Faixa de Antiguidade', how='left'
                    ).fillna(0)
                    hoje_counts_df['total'] = hoje_counts_df['total'].astype(int)
                    hoje_counts_df['data'] = hoje_data 
                except ValueError:
                    st.warning("Data atual ('datas_referencia.txt') inválida.")
                    hoje_data = None 
            else:
                st.warning("Não foi possível carregar ou processar dados de 'hoje' (df_aging).")


            if not df_hist.empty and not hoje_counts_df.empty:
                 df_combinado = pd.concat([df_hist, hoje_counts_df], ignore_index=True)
                 df_combinado = df_combinado.drop_duplicates(subset=['data', 'Faixa de Antiguidade'], keep='last') 
            elif not df_hist.empty:
                 df_combinado = df_hist.copy()
                 st.warning("Dados de 'hoje' não disponíveis para comparação.")
            elif not hoje_counts_df.empty:
                 df_combinado = hoje_counts_df.copy()
                 st.warning("Dados históricos não disponíveis para comparação.")
            else:
                 st.error("Não há dados históricos nem dados de hoje para a análise de aging.")
                 st.stop() 

            df_combinado['data'] = pd.to_datetime(df_combinado['data'])
            df_combinado = df_combinado.sort_values(by=['data', 'Faixa de Antiguidade'])


            st.markdown("##### Comparativo")
            periodo_comp_opts = { "Ontem": 1, "7 dias atrás": 7, "15 dias atrás": 15, "30 dias atrás": 30 }
            periodo_comp_selecionado = st.radio(
                "Comparar 'Hoje' com:", options=periodo_comp_opts.keys(),
                horizontal=True, key="radio_comp_periodo"
            )

            data_comparacao_final = None
            df_comparacao_dados = pd.DataFrame()
            data_comparacao_str = "N/A"

            if hoje_data:
                target_comp_date = hoje_data.date() - timedelta(days=periodo_comp_opts[periodo_comp_selecionado])
                # Passa _repo
                data_comparacao_encontrada, _ = find_closest_snapshot_before(_repo, hoje_data.date(), target_comp_date)

                if data_comparacao_encontrada:
                    data_comparacao_final = pd.to_datetime(data_comparacao_encontrada)
                    data_comparacao_str = data_comparacao_final.strftime('%d/%m')
                    df_comparacao_dados = df_combinado[df_combinado['data'] == data_comparacao_final].copy() 
                    if df_comparacao_dados.empty:
                         st.warning(f"Snapshot de {data_comparacao_str} encontrado, mas sem dados válidos após processamento.")
                         data_comparacao_final = None 
                else:
                    pass 

            cols_linha1 = st.columns(3)
            cols_linha2 = st.columns(3)
            cols_map = {0: cols_linha1[0], 1: cols_linha1[1], 2: cols_linha1[2],
                        3: cols_linha2[0], 4: cols_linha2[1], 5: cols_linha2[2]}

            for i, faixa in enumerate(ordem_faixas_scaffold):
                with cols_map[i]:
                    valor_hoje = 'N/A'
                    delta_text = "N/A"
                    delta_class = "delta-neutral"

                    if not hoje_counts_df.empty:
                        valor_hoje_series = hoje_counts_df.loc[hoje_counts_df['Faixa de Antiguidade'] == faixa, 'total']
                        if not valor_hoje_series.empty:
                            valor_hoje = int(valor_hoje_series.iloc[0])

                            if data_comparacao_final and not df_comparacao_dados.empty:
                                valor_comp_series = df_comparacao_dados.loc[df_comparacao_dados['Faixa de Antiguidade'] == faixa, 'total']
                                if not valor_comp_series.empty:
                                    valor_comparacao = int(valor_comp_series.iloc[0])
                                    delta_abs = valor_hoje - valor_comparacao
                                    delta_perc = (delta_abs / valor_comparacao) if valor_comparacao > 0 else 0
                                    delta_text, delta_class = formatar_delta_card(delta_abs, delta_perc, valor_comparacao, data_comparacao_str)
                                else:
                                     valor_comparacao = 0 
                                     delta_abs = valor_hoje - valor_comparacao
                                     delta_text, delta_class = formatar_delta_card(delta_abs, 0, valor_comparacao, data_comparacao_str)
                            elif hoje_data: 
                                 delta_text = "Sem dados para comparar"
                        else: 
                             valor_hoje = 0 
                             delta_text = "N/A"
                    
                    elif not hoje_data:
                         delta_text = "Dados de hoje indisponíveis"

                    st.markdown(f"""
                    <div class="metric-box">
                        <span class="label">{faixa}</span>
                        <span class="value">{valor_hoje}</span>
                        <span class="delta {delta_class}">{delta_text}</span>
                    </div>
                    """, unsafe_allow_html=True)

            st.divider()

            st.markdown(f"##### Gráfico de Evolução (Últimos 7 dias)")
            
            hoje_filtro_grafico = datetime.now().date()
            data_inicio_filtro_grafico = hoje_filtro_grafico - timedelta(days=6) 
            df_filtrado_grafico = df_combinado[df_combinado['data'].dt.date >= data_inicio_filtro_grafico].copy()

            if df_filtrado_grafico.empty:
                st.warning("Não há dados de aging para os últimos 7 dias.")
            else:
                df_grafico = df_filtrado_grafico.sort_values(by='data')
                df_grafico['Data (Eixo)'] = df_grafico['data'].dt.strftime('%d/%m')
                ordem_datas_grafico = df_grafico['Data (Eixo)'].unique().tolist() 

                # ... (código da paleta de cores e tipo de gráfico) ...
                def lighten_color(hex_color, amount=0.2):
                    try:
                        hex_color = hex_color.lstrip('#')
                        h, l, s = colorsys.rgb_to_hls(*[int(hex_color[i:i+2], 16)/255.0 for i in (0, 2, 4)])
                        new_l = l + (1 - l) * amount
                        r, g, b = colorsys.hls_to_rgb(h, new_l, s)
                        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                    except Exception: return hex_color
                base_color = "#375623"
                palette = [ lighten_color(base_color, 0.85), lighten_color(base_color, 0.70), lighten_color(base_color, 0.55), lighten_color(base_color, 0.40), lighten_color(base_color, 0.20), base_color ]
                color_map = {faixa: color for faixa, color in zip(ordem_faixas_scaffold, palette)}

                tipo_grafico = st.radio(
                    "Selecione o tipo de gráfico:",
                    ("Gráfico de Linha (Comparativo)", "Gráfico de Área (Composição)"),
                    horizontal=True, key="radio_tipo_grafico_aging"
                )

                if tipo_grafico == "Gráfico de Linha (Comparativo)":
                    fig_aging_all = px.line(
                        df_grafico, x='Data (Eixo)', y='total', color='Faixa de Antiguidade',
                        title='Evolução por Faixa de Antiguidade (Últimos 7 dias)', markers=True,
                        labels={"Data (Eixo)": "Data", "total": "Total Chamados", "Faixa de Antiguidade": "Faixa"},
                        category_orders={'Data (Eixo)': ordem_datas_grafico, 'Faixa de Antiguidade': ordem_faixas_scaffold},
                        color_discrete_map=color_map
                    )
                else: 
                    fig_aging_all = px.area(
                        df_grafico, x='Data (Eixo)', y='total', color='Faixa de Antiguidade',
                        title='Composição da Evolução por Antiguidade (Últimos 7 dias)', markers=True,
                        labels={"Data (Eixo)": "Data", "total": "Total Chamados", "Faixa de Antiguidade": "Faixa"},
                        category_orders={'Data (Eixo)': ordem_datas_grafico, 'Faixa de Antiguidade': ordem_faixas_scaffold},
                        color_discrete_map=color_map
                    )

                fig_aging_all.update_layout(height=500, legend_title_text='Faixa')
                st.plotly_chart(fig_aging_all, use_container_width=True)

        except Exception as e:
            st.error(f"Ocorreu um erro ao gerar a aba de Evolução Aging: {e}")
            st.exception(e) 

except Exception as e:
    # Mostra o erro na tela principal
    st.error(f"Ocorreu um erro GERAL ao carregar ou processar os dados: {e}") 
    # Loga o traceback completo para depuração (visível nos logs do Streamlit Cloud/Servidor)
    import traceback
    st.exception(e) 
    # Opcional: Parar a execução se for um erro crítico
    # st.stop() 

st.markdown("---")
# Atualiza versão no rodapé
st.markdown(""" 
<p style='text-align: center; color: #666; font-size: 0.9em; margin-bottom: 0;'>v0.9.34 | Este dashboard está em desenvolvimento.</p>
<p style='text-align: center; color: #666; font-size: 0.9em; margin-top: 0;'>Desenvolvido por Leonir Scatolin Junior</p>
""", unsafe_allow_html=True)
