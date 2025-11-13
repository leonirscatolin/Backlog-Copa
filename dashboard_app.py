with tab2:
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
            
            # --- INÍCIO DA LÓGICA DE PARETO AUTOMÁTICA ---
            chart_data = df_aging.groupby(['Atribuir a um grupo', 'Faixa de Antiguidade']).size().reset_index(name='Quantidade')
            group_totals = chart_data.groupby('Atribuir a um grupo')['Quantidade'].sum().sort_values(ascending=False)

            if not group_totals.empty:
                df_pareto = group_totals.to_frame(name='Total')
                df_pareto['CumulativePct'] = df_pareto['Total'].cumsum() / df_pareto['Total'].sum()
                
                total_backlog_geral = df_pareto['Total'].sum()
                total_grupos_geral = len(df_pareto)
                
                pareto_limit = 0.80
                num_groups_for_80_pct = 1
                if df_pareto['CumulativePct'].iloc[0] <= pareto_limit:
                    try:
                        groups_under_80 = df_pareto[df_pareto['CumulativePct'] <= pareto_limit]
                        num_groups_for_80_pct = len(groups_under_80) + 1
                    except Exception:
                        num_groups_for_80_pct = 1 # Fallback
                
                if num_groups_for_80_pct > total_grupos_geral:
                    num_groups_for_80_pct = total_grupos_geral

                final_pareto_groups = df_pareto.head(num_groups_for_80_pct)
                actual_pct = final_pareto_groups.iloc[-1]['CumulativePct']
                actual_call_count = final_pareto_groups['Total'].sum()
                
                top_3_groups = group_totals.head(3)
                
                summary_text = [f"📊 **Análise Rápida (Princípio de Pareto):**\n"]
                summary_text.append(f"* Nossa análise mostra que **{num_groups_for_80_pct}** grupos (de um total de **{total_grupos_geral}**) são responsáveis por **{actual_call_count}** chamados, o que representa **{actual_pct:.0%}** de todo o backlog (de {total_backlog_geral} chamados).\n")
                summary_text.append(f"* Os 3 grupos de maior impacto são:\n")
                
                list_items = []
                for i, (group, count) in enumerate(top_3_groups.items(), 1):
                    list_items.append(f"    {i}.  **{group}** ({count} chamados)")
                summary_text.append("\n".join(list_items))
                
                st.info("\n".join(summary_text))
            
            # --- FIM DA LÓGICA DE PARETO ---

            orientation_choice = st.radio( "Orientação do Gráfico:", ["Vertical", "Horizontal"], index=0, horizontal=True )
            
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
                fig_stacked_bar.update_layout(height=dynamic_height, legend_title_text='Antiguidade')
            else:
                fig_stacked_bar = px.bar( chart_data, x='Atribuir a um grupo', y='Quantidade', color='Faixa de Antiguidade', title="Composição da Idade do Backlog por Grupo", labels={'Quantidade': 'Qtd. de Chamados', 'Atribuir a um grupo': 'Grupo'}, category_orders={'Atribuir a um grupo': sorted_new_labels, 'Faixa de Antiguidade': ordem_faixas}, color_discrete_map=color_map, text_auto=True )
                fig_stacked_bar.update_traces(textangle=0, textfont_size=12)
                fig_stacked_bar.update_layout(height=600, xaxis_title=None, xaxis_tickangle=-45, legend_title_text='Antiguidade')
            st.plotly_chart(fig_stacked_bar, use_container_width=True)
        else:
            st.warning("Nenhum dado para gerar o report visual.")
