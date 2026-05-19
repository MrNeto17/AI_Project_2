import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import pickle

def main():
    print("=" * 60)
    print("  SISTEMA DE TREINO DE MACHINE LEARNING - PRODUÇÃO RÁPIDA  ")
    print("=" * 60)

    # 1. CARREGAR OS DATASETS
    print("\n[1/6] A carregar os ficheiros CSV...")
    try:
        sales_df = pd.read_csv("dataset(.csv)/sales.csv")
        calendar_df = pd.read_csv("dataset(.csv)/calendar.csv")
        print("-> Ficheiros carregados com sucesso!")
    except FileNotFoundError as e:
        print(f"Erro: Garanta que os ficheiros 'sales.csv' e 'calendar.csv' estão na mesma pasta. ({e})")
        return

    # 2. LIMPEZA DE DADOS (Dedup de Menus conforme o DATA_OVERVIEW.md)
    # Ignorar linhas com parent_id para não contar ingredientes/acompanhamentos a duplicar
    sales_df_filtered = sales_df[sales_df['parent_id'].isna()].copy()
    print(f"-> Filtro de menus aplicado. Registos válidos: {len(sales_df_filtered)} de {len(sales_df)}")

    # Juntar as vendas com o calendário para obter o contexto do dia (Clima e Eventos)
    data = pd.merge(sales_df_filtered, calendar_df, on="date", how="inner")
    print(f"-> Dados de vendas agregados com sucesso ao calendário.")

    # 3. ENGENHARIA DE ATRIBUTOS (FEATURE ENGINEERING)
    print("\n[2/6] A processar atributos temporais e a agregar procura...")
    # Extrair Hora e Minuto numéricos a partir do texto do campo 'hour'
    data['datetime_hour'] = pd.to_datetime(data['hour'], format='%H:%M')
    data['hour_num'] = data['datetime_hour'].dt.hour
    data['minute_num'] = data['datetime_hour'].dt.minute

    # Agrupar por Dia, Hora exata, Produto e Contexto para somar a quantidade pedida
    group_cols = ['date', 'week_day', 'hour_num', 'minute_num', 'event', 'weather', 'product_name']
    grouped_data = data.groupby(group_cols, as_index=False)['quantity'].sum()
    print(f"-> Total de instâncias contextuais criadas: {len(grouped_data)} linhas.")

    # 4. MAPEAMENTO DE TEXTO PARA NÚMERO (DATA ENCODING)
    print("\n[3/6] A converter variáveis categóricas (texto) para numéricas...")
    weekday_map = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}
    event_map = {'NONE': 0, 'HOLIDAY': 1, 'SMALL_EVENT': 2, 'BIG_EVENT': 3}
    weather_map = {'NOT_RAINING': 0, 'RAINING': 1}

    # Criar mapeamento único e estático para os produtos do menu
    unique_products = sorted(grouped_data['product_name'].unique())
    product_map = {prod: i for i, prod in enumerate(unique_products)}
    
    print("   Produtos detetados e mapeados:")
    for prod, num in product_map.items():
        print(f"     * {prod} -> {num}")

    # Aplicar dicionários de mapeamento
    grouped_data['week_day_num'] = grouped_data['week_day'].map(weekday_map)
    grouped_data['event_num'] = grouped_data['event'].map(event_map)
    grouped_data['weather_num'] = grouped_data['weather'].map(weather_map)
    grouped_data['product_num'] = grouped_data['product_name'].map(product_map)

    # Remover quaisquer valores nulos gerados por falhas de mapeamento
    grouped_data = grouped_data.dropna(subset=['week_day_num', 'event_num', 'weather_num', 'product_num'])

    # 5. DIVISÃO DOS DADOS (HOLDOUT METHOD: 70% TREINO / 30% TESTE)
    print("\n[4/6] A aplicar o Método Holdout (70/30)...")
    X = grouped_data[['week_day_num', 'hour_num', 'minute_num', 'event_num', 'weather_num', 'product_num']]
    y = grouped_data['quantity']

    # Fixamos a random_state (seed) para garantir repetibilidade na auditoria do professor
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.30, random_state=42)
    print(f"-> Matriz de Treino: {X_train.shape[0]} amostras")
    print(f"-> Matriz de Teste: {X_test.shape[0]} amostras")

    # 6. TREINO DA ÁRVORE DE DECISÃO
    print("\n[5/6] A induzir o modelo DecisionTreeRegressor...")
    model = DecisionTreeRegressor(max_depth=10, min_samples_split=5, random_state=42)
    model.fit(X_train, y_train)
    print("-> Modelo treinado com sucesso!")

    # 7. AVALIAÇÃO E MÉTRICAS DE PERFORMANCE
    print("\n[6/6] A calcular métricas de validação...")
    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)

    # Cálculo dos erros (MSE, MAE) e R² Score para o Relatório
    mse_test = mean_squared_error(y_test, y_pred_test)
    mae_test = mean_absolute_error(y_test, y_pred_test)
    r2_test = r2_score(y_test, y_pred_test)

    print("-" * 40)
    print(f" Erro Médio Absoluto (MAE): {mae_test:.3f} unidades")
    print(f" Erro Quadrático Médio (MSE): {mse_test:.3f}")
    print(f" Coeficiente de Determinação (R²): {r2_test:.3f}")
    print("-" * 40)

    # EXPORTAR O MODELO E DICIONÁRIOS
    # Guardamos os mapeamentos juntos com o modelo para a Web App saber converter os inputs depois!
    model_data = {
        "model": model,
        "product_map": product_map,
        "weekday_map": weekday_map,
        "event_map": event_map,
        "weather_map": weather_map
    }

    with open("production_model.pkl", "wb") as f:
        pickle.dump(model_data, f)
    print("\n[SUCESSO] Ficheiro 'production_model.pkl' exportado para a Web App!")
    print("=" * 60)

if __name__ == "__main__":
    main()