import streamlit as st
import sqlite3
import pandas as pd
import datetime

st.set_page_config(page_title="Gestor Financeiro", layout="wide")

# Inicializa Banco
conn = sqlite3.connect("monitor_data.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS metas_financeiras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        categoria TEXT NOT NULL,
        valor_alvo REAL NOT NULL,
        valor_atual REAL DEFAULT 0.0,
        data_limite TEXT
    )
""")
conn.commit()

# Menu Lateral (Abas)
aba = st.sidebar.radio("Navegação", ["🎯 Metas & Orçamento", "📊 Gráficos", "♿ Acessibilidade & Guia"])

if aba == "🎯 Metas & Orçamento":
    st.title("🎯 Gestão de Metas Financeiras")
    
    with st.form("nova_meta"):
        col1, col2 = st.columns(2)
        nome = col1.text_input("Nome da Meta")
        cat = col2.selectbox("Categoria", ["Reserva de Emergência", "Investimentos", "Viagem", "Tecnologia", "Outros"])
        alvo = col1.number_input("Valor Alvo (R$)", min_value=0.0)
        atual = col2.number_input("Valor Atual (R$)", min_value=0.0)
        limite = st.date_input("Data Limite")
        
        if st.form_submit_button("Salvar Meta"):
            c.execute("INSERT INTO metas_financeiras (nome, categoria, valor_alvo, valor_atual, data_limite) VALUES (?, ?, ?, ?, ?)",
                      (nome, cat, alvo, atual, str(limite)))
            conn.commit()
            st.success("Meta salva com sucesso!")

    st.subheader("Minhas Metas")
    df = pd.read_sql_query("SELECT * FROM metas_financeiras", conn)
    st.dataframe(df, use_container_width=True)

elif aba == "📊 Gráficos":
    st.title("📊 Visualização de Desempenho")
    df = pd.read_sql_query("SELECT nome, valor_alvo, valor_atual FROM metas_financeiras", conn)
    if not df.empty:
        st.bar_chart(df.set_index("nome"))
    else:
        st.info("Nenhuma meta cadastrada.")

elif aba == "♿ Acessibilidade & Guia":
    st.title("♿ Guia de Uso")
    st.write("Sistema de monitoramento financeiro pessoal simplificado para a web.")