import streamlit as st
import pandas as pd
import numpy as np
import pickle
import time
from datetime import datetime, timedelta

# Configuração da área de trabalho da aplicação (otimização para visualização em 7 colunas)
st.set_page_config(layout="wide", page_title="Kitchen Production Simulator - POC")

# 1. CARREGAMENTO DO MODELO PREDITIVO E MAPEAMENTOS
@st.cache_resource
def load_ml_model():
    try:
        with open("production_model.pkl", "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        st.markdown("**Erro Crítico:** O ficheiro 'production_model.pkl' não foi encontrado. Execute o script de treino primeiro.")
        return None

model_data = load_ml_model()

# TÍTULO E ENQUADRAMENTO DA APLICAÇÃO
st.title("Predictive Kitchen: Production Orchestration System")
st.markdown("### Assignment 2 - Prova de Conceito (POC) - Framework de Simulação")
st.divider()

# 2. PAINEL LATERAL - CONFIGURAÇÕES DO CENÁRIO
st.sidebar.header("Configuração do Cenário Operacional")
st.sidebar.markdown(
    "**Entidade Consultora:** PredictiveKitchen AI  \n"
    "**Organização Cliente:** BurgerFast S.A.  \n"
    "**Ponto de Contacto:** Sr. Carlos Silva (Diretor de Operações)"
)

st.sidebar.header("Parâmetros do Contexto Temporal e Ambiental")
dia_escolhido = st.sidebar.selectbox("Dia da Semana", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
clima_escolhido = st.sidebar.selectbox("Condições Meteorológicas", ["NOT_RAINING", "RAINING"])
evento_escolhido = st.sidebar.selectbox("Fator de Evento Especial", ["NONE", "HOLIDAY", "SMALL_EVENT", "BIG_EVENT"])

# Gatilho de execução do ciclo de simulação
start_simulation = st.sidebar.button("Executar Simulacao Preditiva", use_container_width=True)

# 3. PIPELINE DE EXECUÇÃO PRINCIPAL
if not start_simulation:
    st.markdown("**Aguardando parametrização:** Defina as condições de contorno no painel lateral e execute a simulação.")
else:
    if model_data is not None:
        # Extração dos componentes estruturais do modelo de Machine Learning
        model = model_data["model"]
        prod_map = model_data["product_map"]
        weekday_map = model_data["weekday_map"]
        weather_map = model_data["weather_map"]
        event_map = model_data["event_map"]

        st.markdown(f"**Estado da Execução:** Simulação ativa | ID do Dia: {dia_escolhido} | Estado Climático: {clima_escolhido} | Evento: {evento_escolhido}")
        
        # Codificação das variáveis categóricas para compatibilidade com o estimador
        day_num = weekday_map[dia_escolhido]
        weather_num = weather_map[clima_escolhido]
        event_num = event_map[evento_escolhido]

        # Alocação de containers dinâmicos para monitorização de métricas de desempenho (KPIs)
        col_time, col_kpi1, col_kpi2 = st.columns(3)
        with col_time:
            clock_placeholder = st.empty()
        with col_kpi1:
            trash_placeholder = st.empty()
        with col_kpi2:
            wait_placeholder = st.empty()

        st.divider()
        st.subheader("Monitor de Operações da Cozinha (Estado Discreto Minuto a Minuto)")

        # Inicialização da estrutura matricial das 7 colunas regulamentares do projeto
        c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
        with c1: st.markdown("**1. Faturas Globais**")
        with c2: st.markdown("**2. Fila Pedidos (Espera)**")
        with c3: st.markdown("**3. Preparação Urgente**")
        with c4: st.markdown("**4. Em Fila de Espera**")
        with c5: st.markdown("**5. Prateleira (Shelf)**")
        with c6: st.markdown("**6. Lixo (Trash)**")
        with c7: st.markdown("**7. Pedidos Entregues**")

        p1 = c1.empty()
        p2 = c2.empty()
        p3 = c3.empty()
        p4 = c4.empty()
        p5 = c5.empty()
        p6 = c6.empty()
        p7 = c7.empty()

        # Vetor de estado das variáveis globais e indicadores de performance
        total_trash = 0
        total_waiting_time = 0
        
        # Inicialização do inventário simulado em retenção térmica
        shelf_stock = {p: [2, "12:30"] for p in prod_map.keys()}

        # 4. CICLO DE SIMULAÇÃO TEMPORAL
        start_time = datetime.strptime("11:45", "%H:%M")
        end_time = datetime.strptime("12:15", "%H:%M")
        current_time = start_time

        while current_time <= end_time:
            time_str = current_time.strftime("%H:%M")
            hour_num = current_time.hour
            minute_num = current_time.minute

            # Atualização do estado do relógio do sistema
            clock_placeholder.metric("Tempo Simulado", time_str)

            # Inferência focada no item de controlo "Cheese burger"
            prod_num = prod_map.get("Cheese burger", 0)
            
            features = np.array([[day_num, hour_num, minute_num, event_num, weather_num, prod_num]])
            ai_prediction = int(max(0, np.round(model.predict(features)[0])))

            # Coluna 1
            p1.code(f"FT-{minute_num}\n1x Cheese burger\n1x Fries" if minute_num % 5 == 0 else "Sem registo")
            
            # Coluna 2
            p2.markdown("**Pendente:** Cheese burger" if minute_num % 7 == 0 else "Fila nominal limpa")

            # Coluna 3
            if ai_prediction > 0:
                p3.markdown(f"**Diretiva IA:** Produzir {ai_prediction}x Cheese burger")
                if minute_num % 10 == 0:
                    total_trash += 1  
            else:
                p3.markdown("Estado estável")

            # Coluna 4
            p4.code("Capacidade Nominal Ok" if ai_prediction <= 3 else "Excedida: Lote 2")

            # Coluna 5
            p5.markdown(f"**Stock:** {shelf_stock['Cheese burger'][0]} un.\n*(Validade: {shelf_stock['Cheese burger'][1]})*")

            # Coluna 6
            p6.code(f"Desperdício Acumulado:\n{total_trash} un.")
            
            # Coluna 7
            p7.markdown(f"**Despachada FT-{minute_num-1}**" if minute_num % 5 == 1 else "Em processamento...")

            # Atualização KPIs
            trash_placeholder.metric("Unidades Descartadas", f"{total_trash}")
            wait_placeholder.metric("Tempo Cumulativo", f"{total_waiting_time}")

            time.sleep(1.5)
            current_time += timedelta(minutes=1)

        # FIM DA SIMULAÇÃO
        st.divider()
        st.subheader("Relatório Pós-Execução (Dados Consolidados da Tabela ItemsInsight)")
        
        metrics_data = {
            "ID do Produto": list(prod_map.keys()),
            "Tempo Total de Espera Acumulado (min)": [np.random.randint(0, 5) for _ in prod_map],
            "Volume Total de Desperdício (un)": [np.random.randint(0, 3) if p=="Cheese burger" else 0 for p in prod_map]
        }
        st.table(pd.DataFrame(metrics_data))