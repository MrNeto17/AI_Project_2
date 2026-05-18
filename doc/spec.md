# Specification Guide: Sistema de Previsão e Orquestração de Produção

## 1. Lógica do Algoritmo

### 1.1. Cálculo da Média Ponderada Histórica (VALUEs)
* **Objetivo**: Calcular a base histórica de pedidos para o dia atual com base nas semanas anteriores.
* **Âmbito temporal**: janela adaptável de 8 semanas / 8 dias da mesma categoria, ou menos se não houver dados suficientes.
* **Lógica de ponderação**: Os dados mais recentes têm maior peso devido ao seu valor preditivo.
* **Fórmula base**:
  VALUEs = (8 * SEGUNDA_PASSADA + 7 * DUAS_SEGUNDAS_PASSADAS + 6 * TRES_SEGUNDAS_PASSADAS + ...) / (8 + 7 + 6 + ...)
* **Especificidade**: O cálculo é realizado para cada time window específica para cada Produto de Produção (correspondente ao seu TEMPO_PRATELEIRA) e de forma individual para cada Produto de Produção.

### 1.2. Percentagens de Diferenciação (Contexto)
* **Fatores contextuais**: Event (None, Holiday, Small Special Event, Big Special Event) e Weather (Not Raining, Raining).
* **Cálculo de base (atualização em base de dados)**:
  * É calculada a média global de todos os dias presentes no dataset (para cada time window específica para cada Produto de Produção (correspondente ao seu TEMPO_PRATELEIRA) e de forma individual para cada Produto de Produção).
  * É calculada a média específica para cada tipo de Evento e para cada tipo de Weather (para cada time window específica para cada Produto de Produção (correspondente ao seu TEMPO_PRATELEIRA) e de forma individual para cada Produto de Produção).
  * A percentagem de diferenciação (aumento ou diminuição de pedidos) resulta da relação entre estes valores (para cada time window específica para cada Produto de Produção (correspondente ao seu TEMPO_PRATELEIRA) e de forma individual para cada Produto de Produção).
* **Exemplo Prático**: Dia 20/04/2026, Monday, Holiday, Not Raining (para beef Burger que tem um TEMPO_PRATELEIRA = 20 min, entao por exemplo natime window = 13:00h - 13:20h):
  * Percentagem de diferenciação (Holiday) = 0.85 (diminuição de pedidos).
  * Percentagem de diferenciação (Not Raining) = 1.20 (aumento de pedidos).
  * CALCULO: VALUEs * 0.85 * 1.20 (a ser aplicado para aquela tie_window especifica).

### 1.3. Ajuste por Multiplicador Manual
* **Objetivo**: Permitir que o Gerente adapte manualmente a estimativa gerada pelo algoritmo.
* **Comportamento**: Aumenta ou diminui a previsão através de um fator direto.
  * Exemplo: Fator de 1.1 aumenta a venda em 10%.
  * Exemplo: Fator de 0.9 diminui a venda em 10%.
* **Aplicação na fórmula**: VALUEs * 0.85 * 1.20 * MULTIPLICADOR_MANUAL.

### 1.4. Ajuste Dinâmico (MULTIPLICADOR_PROPRIO_DIA)
* **Objetivo**: Corrigir e retroalimentar o algoritmo em tempo real com base no desvio face às vendas reais do próprio dia.
* **Condição de ativação**: Só é válido e aplicado após o sistema registar um valor mínimo de pedidos no dia (exemplo: 20 pedidos)
* **Limte**: Esta limitado num intervalo de [0.5,5], se o valor calculado estiver fora do intervalo assume o valor maximo ou minimo. Se o valor for 0 assume 1.0.
* **Lógica de ponderação**: Os dados das últimas horas são mais valiosos por revelarem a afluência do momento atual.
* **Tratamento de Casos Limite Matemáticos (Divisão por Zero / Penalização)**:
  * Problema: Se a previsão for 0 e houver 1 pedido real, ocorre um erro de divisão por zero (1/0). Se a previsão for 5 e existirem 0 pedidos reais, o valor 0 penaliza fortemente o multiplicador em potências ponderadas.
  * Solução (Suavização de Laplace / Floor Operacional):
    Valor do Intervalo = (Real Orders + 1) / (Prediction + 1)
* **Função de peso exponencial**: f(x) = x^(1.2).
* **Exemplo de Cálculo do Multiplicador Ponderado (beef Burger)**:
  * Janela 11:00h às 11:19h: Previsão às 10:55h = 3 | Pedidos Reais = 2 | Valor = 2/3 = 0.66
  * Janela 11:20h às 11:39h: Previsão às 11:15h = 5 | Pedidos Reais = 7 | Valor = 7/5 = 1.4
  * Janela 11:40h às 11:59h: Previsão às 11:35h = 12 | Pedidos Reais = 12 | Valor = 12/12 = 1.0
  * Janela 12:00h às 12:19h: Previsão às 11:55h = 10 | Pedidos Reais = 6 | Valor = 6/10 = 0.6
  * Janela 12:20h às 12:39h: Previsão às 12:15h = 14 | Pedidos Reais = 15 | Valor = 15/14 = 1.07
  * Execução da previsão às 12:35h e às 12:55h: O cálculo do MULTIPLICADOR_PROPRIO_DIA para a previsão das 12:55h usa a fórmula: (6.90 * 1.07 + 5.29 * 0.6 + 3.74 * 1.0 + 2.30 * 1.4 + 1 * 0.66) / (6.90 + 5.29 + 3.74 + 2.30 + 1). Nota: A previsão das 12:35h não pode usar os dados da janela das 12:20h às 12:49h porque esta ainda não está completa, recorrendo assim ao histórico imediatamente anterior.
  * vai haver uma tabela na base de dados onde o numero de pedidos previstos, e o numero de pedidos reais que vai ser preenchida em tempo real, assimque acaba cada time_window. assim esta tabela vai poder ser consultada para calcular o MULTIPLICADOR_PROPRIO_DIA. a tabela vai ter o formato
time_window,prod,nr_predicted_orders,nr_real_orders
11:00_11:09,fries,x,x
11:10_11:19,fries,x,x
...
23:50_23:59,fries,x,x
11:00_11:19,beef_burger,x,x
11:20_11:39,beef_burger,x,x
...
23:40_23:59,beef_burger,x,x
11:00_11:19,chicken_burger,x,x
11:20_11:39,chicken_burger,x,x
...
23:40_23:59,chicken_burger,x,x
11:00_11:14,fish_burger,x,x
11:15_11:29,fish_burger,x,x
...
23:45_23:59,fish_burger,x,x
11:00_11:14,vegan_burger,x,x
11:15_11:29,vegan_burger,x,x
...
23:45_23:59,vegan_burger,x,x
11:00_11:29,apple_pie,x,x
11:30_11:59,apple_pie,x,x
...
23:30_23:59,apple_pie,x,x


### 1.5. Cálculo Final da Previsão
* **Fórmula Completa**:
  CALCULO(time_window,prod,week_day) = VALUE(time_window,prod,week_day) * PCT_DIFERENCIAÇÃO_EVENT(time_window,prod) * PCT_DIFERENCIAÇÃO_WEATHER(time_window,prod) * MULTIPLICADOR_MANUAL(global para o dia) * MULTIPLICADOR_PROPRIO_DIA (ultimo valor calculado - ha um novo a cada time_window,prod)
* **Aplicação**: Os valores de VALUEs, PCT_DIFERENCIAÇÃO_EVENT e PCT_DIFERENCIAÇÃO_WEATHER são calculados e aplicados especificamente para cada time window e para cada Produto de Produção.
* * **Arredondamento**: O valor final obtido é arredondado às unidades para cima, por definição (default).

NOTA IMPORTANTE: Para os valores VALUEs, PCT_DIFERENCIAÇÃO_EVENT, PCT_DIFERENCIAÇÃO_WEATHER que têm de ser calculados para cada time window específica para cada Produto de Produção (correspondente ao seu TEMPO_PRATELEIRA) e de forma individual para cada Produto de Produção, a forma de proceder é a seguinte:
- para VALUEs calculado em run-time (ou seja tem de ser calculado todos os dias): no algoritmo antes de todas as computações começarem calcula os valores para aquele dia todo para todas as time windows. para os nosso Produtos de Produção existem 4 time_windows diferentes (4 TEMPO_PRATELEIRA diferentes): 10min, 20min, 15min, 30min. Então vão ter de ser calculados os valores VALUE para 4 disposições do dia (de 10 em 10(fries), 20 em 20 (beef_burger,chicken_burger), 15 em 15(fish_burger,vegan_burger), e 30 em 30(apple_pie)) para cada dia, no inicio do algoritmo
week_day,time_window,prod,prediction
monday,11:00_11:09,fries,x
monday,11:10_11:19,fries,x
...
monday,23:50_23:59,fries,x
monday,11:00_11:19,beef_burger,x
monday,11:20_11:39,beef_burger,x
...
monday,23:40_23:59,beef_burger,x
monday,11:00_11:19,chicken_burger,x
monday,11:20_11:39,chicken_burger,x
...
monday,23:40_23:59,chicken_burger,x
monday,11:00_11:14,fish_burger,x
monday,11:15_11:29,fish_burger,x
...
monday,23:45_23:59,fish_burger,x
monday,11:00_11:14,vegan_burger,x
monday,11:15_11:29,vegan_burger,x
...
monday,23:45_23:59,vegan_burger,x
monday,11:00_11:29,apple_pie,x
monday,11:30_11:59,apple_pie,x
...
monday,23:30_23:59,apple_pie,x
tuesday,11:00_11:09,fries,x
tuesday,11:10_11:19,fries,x
...
tuesday,23:50_23:59,fries,x
tuesday,11:00_11:19,beef_burger,x
tuesday,11:20_11:39,beef_burger,x
...
tuesday,23:40_23:59,beef_burger,x
tuesday,11:00_11:19,chicken_burger,x
tuesday,11:20_11:39,chicken_burger,x
...
tuesday,23:40_23:59,chicken_burger,x
tuesday,11:00_11:14,fish_burger,x
tuesday,11:15_11:29,fish_burger,x
...
tuesday,23:45_23:59,fish_burger,x
tuesday,11:00_11:14,vegan_burger,x
tuesday,11:15_11:29,vegan_burger,x
...
tuesday,23:45_23:59,vegan_burger,x
tuesday,11:00_11:29,apple_pie,x
tuesday,11:30_11:59,apple_pie,x
...
tuesday,23:30_23:59,apple_pie,x
- para PCT_DIFERENCIAÇÃO_EVENT, PCT_DIFERENCIAÇÃO_WEATHER: calculados a nivel de base de dados (vão ter uma tabela especifica com todas as time_windows das 4 disposições diferentes para um dia (de 10 em 10(fries), 20 em 20 (beef_burger,chicken_burger), 15 em 15(fish_burger,vegan_burger), e 30 em 30(apple_pie)), este calculo na base de dados vai calcular a média simples global para cada time_window, depois vai calcular a média simples para cada time_window para cada tipo de evento e para cada tipo de weather individualmente, e depois vai calculara percentagem de diferenciação da relação entre estes valores. esta tabela vai ter o formato:
time_window,prod,pct_dif_raining,pct_dif_not_raining,pct_dif_event_none,pct_dif_event_holiday,pct_dif_event_small,pct_dif_event_big
11:00_11:09,fries,x,x,x,x,x,x
11:10_11:19,fries,x,x,x,x,x,x
...
23:50_23:59,fries,x,x,x,x,x,x
11:00_11:19,beef_burger,x,x,x,x,x,x
11:20_11:39,beef_burger,x,x,x,x,x,x
...
23:40_23:59,beef_burger,x,x,x,x,x,x
11:00_11:19,chicken_burger,x,x,x,x,x,x
11:20_11:39,chicken_burger,x,x,x,x,x,x
...
23:40_23:59,chicken_burger,x,x,x,x,x,x
11:00_11:14,fish_burger,x,x,x,x,x,x
11:15_11:29,fish_burger,x,x,x,x,x,x
...
23:45_23:59,fish_burger,x,x,x,x,x,x
11:00_11:14,vegan_burger,x,x,x,x,x,x
11:15_11:29,vegan_burger,x,x,x,x,x,x
...
23:45_23:59,vegan_burger,x,x,x,x,x,x
11:00_11:29,apple_pie,x,x,x,x,x,x
11:30_11:59,apple_pie,x,x,x,x,x,x
...
23:30_23:59,apple_pie,x,x,x,x,x,x

EXEMPLO: para a pct_dif_raining para time_window=11:00_11:19 e  item beef_burger, o calculo vai ser raining_days_mean(11:00_11:19,beef_burger)/global_mean(11:00_11:19,beef_burger) 
if the division result is 0 or divide by 0, make the result be the default 1




Esta tabela não é para ser atualizada em tempo real durnate os dias, apenas uma vez no final de cada dia


### 1.6. Regras de Orquestração e Capacidade Máxima
* **Restrição de Capacidade**: Se o sistema prever uma quantidade superior à capacidade máxima instantânea do equipamento, a produção é dividida em rondas extra.
* **Variáveis Universais por Item**:
  * Tempo de Produção: Tempo necessário para o item ficar disponível.
  * Buffer de Preparação: Constante universal de 1 minuto adicionada ao tempo de produção (Tempo de Produção + 1).
  * Tempo de Prateleira: Período em que o produto mantém a qualidade para venda após estar pronto.
  * Capacidade Máxima (MAX_CAPACITY): Limite de unidades produzidas em simultâneo.
* **Matriz de Produtos de Produção**:
  * Fries: Tempo Produção = 2 min (3 min total com buffer) | Tempo Prateleira = 10 min | Max Capacity = 24.
  * beef Burger: Tempo Produção = 4 min (5 min total com buffer) | Tempo Prateleira = 20 min | Max Capacity = 8.
  * Chicken Burger: Tempo Produção = 4 min (5 min total com buffer) | Tempo Prateleira = 20 min | Max Capacity = 8.
  * Fish Burger: Tempo Produção = 6 min (7 min total com buffer) | Tempo Prateleira = 15 min | Max Capacity = 6.
  * Vegan Burger: Tempo Produção = 6 min (7 min total com buffer) | Tempo Prateleira = 15 min | Max Capacity = 6.
  * Apple Pie: Tempo Produção = 10 min (11 min total com buffer) | Tempo Prateleira = 30 min | Max Capacity = 5.
* **Exemplo de Escalonamento e Capacidade Extra (beef Burger)**:
  * Horário de funcionamento: Cozinha aberta das 10:30h às 23:59h (Público: 11:00h às 23:59h).
  * Janela de cálculo: O número previsto deve ser calculado a cada 20 minutes (tempo de prateleira), com a antecedência do tempo de produção total (5 minutos).
  * Fluxo regular:
    * Alerta 10:55h: Cozinhar X1 para estar pronto e disponível das 11:00h às 11:19h.
    * Alerta 11:15h: Cozinhar X2 para estar pronto e disponível das 11:20h às 11:39h.
    * Alerta 11:35h: Cozinhar X3 para estar pronto e disponível das 11:40h às 11:59h.
    * Alerta 11:55h: Cozinhar X4 para estar pronto e disponível das 12:00h às 12:19h.
    * Alerta 23:15h: Cozinhar X5 para estar pronto e disponível das 23:20h às 23:39h.
    * Alerta 23:35h: Cozinhar X6 para estar pronto e disponível das 23:40h às 23:59h.
  * Cenário de Lotação Máxima Excedida:
    * Alerta 10:55h: Sistema prevê e pede 14 beef Burgers. Sendo a capacidade máxima 8, o sistema ordena cozinhar 8 imediatamente (disponíveis das 11:00h às 11:19h).
    * Ronda Extra às 11:00h: Sistema ordena cozinhar as 6 unidades restantes (14 menos 8), ficando prontas e disponíveis na janela deslizada das 11:05h às 11:24h.
    * Salvaguarda: Às 11:15h o sistema pede 7 beef Burgers e a produção inicia-se mesmo que ainda existam unidades na prateleira para evitar riscos de rutura; eventuais excessos serão corrigidos pelo MULTIPLICADOR_PROPRIO_DIA na iteração seguinte.

---

## 2. Lógica da Aplicação

### 2.1. Premissas do Sistema
* **Foco Exclusivo**: O algoritmo e monitorização aplicam-se apenas a Produtos de Produção (artigos cozinháveis/preparados), identificados como o verdadeiro gargalo (bottleneck) para uma cozinha rápida.
* **Simplificações Operacionais**:
  * O tempo de montagem final dos pedidos é desprezado.
  * O tempo entre a submissão do pedido e a entrega ao cliente com ingredientes prontos é de no máximo 3 minutos.
  * O stock de matérias-primas é considerado ilimitado.
* **Regra Absoluta de Atendimento**: Todos os pedidos registados têm de ser obrigatoriamente atendidos.

### 2.2. Gestão de Filas e Infraestrutura de Dados
* **ORDERS_QUEUE**: Fila de espera por item para pedidos que não foram antecipados pela previsão atual (pedidos não previstos).
* **ITEM_QUEUE**: Fila de espera por item para produtos cuja produção foi agendada mas aguarda a libertação de espaço na capacidade máxima do equipamento.
* **Controlo de Anomalias (MAX_LIMIT da ITEM_QUEUE)**:
  * A ITEM_QUEUE possui um limite máximo para evitar acumulações incorretas.
  * Fórmula de Cálculo: MAX_LIMIT = (X + Y) - (Z + W)
  * X = Quantidade de pedidos na ORDERS_QUEUE para esse tipo de item.
  * Y = Valor da previsão calculada (CALCULO) para a janela de tempo atual.
  * Z = Quantidade de itens atualmente em preparação para esse tipo de item.
  * W = Quantidade de pedidos da janela de tempo atual que já foram respondidos.

### 2.3. Fluxo de Execução Cíclico (Sequential Processing Loop)
* **Execução**: Processamento contínuo gerido por um simulador de eventos discretos que corre minuto a minuto.
* **Ordem Sequencial Operacional**:
  1. Check Expirations: Verificar e remover itens cujo tempo de prateleira expirou.
  2. Process Incoming Orders: Processar a entrada de novos pedidos e associá-los ao stock ou filas.
  3. Schedule Production: Agendar e disparar ordens de produção conforme as previsões e necessidades.

### 2.4. Ciclo de Vida do Item (Máquina de Estados)
* **Estados sequenciais**: SCHEDULED ou ACTUAL_ORDER (imediato) -> COOKING (Tempo de Preparação) -> READY (imediato) -> ON_SHELF (Tempo de Prateleira) -> EXPIRED ou TRASH (imediato).

### 2.5. Ações Operacionais face a Pedidos e Fins de Prazo
* **Ação 1: Item pedido está disponível na PRATELEIRA**:
  * O produto é retirado da PRATELEIRA para satisfazer o pedido.
  * Critério de seleção: É recolhido o item com o prazo de validade mais próximo de expirar.
  * O pedido é movido diretamente para o histórico de ORDERS_ANSWERED.
* **Ação 2: Item atinge o limite do TEMPO_PRATELEIRA**:
  * O item expira e é enviado para o TRASH no minuto imediatamente a seguir (Exemplo: disponível das 11:00h às 11:19h, é movido para o lixo às 11:20h).
  * Regra de fecho: Às 0:00h todos os itens em stock na prateleira são obrigatoriamente descartados para o TRASH.
* **Ação 3: Item é pedido mas não está disponível na PRATELEIRA**:
  * O sistema verifica se existe capacidade livre na máquina para ser cozinhado (não atingiu o MAX_CAPACITY).
  * Se não houver espaço: Entra na ITEM_QUEUE e aguarda por uma vaga, reavaliando a cada minuto.
  * Se houver ou assim que houver espaço: É colocado em produção.
  * Se já existirem itens equivalentes em cozedura: O item que está a cozinhar não responderá a esse pedido específico de imediato, mas a ação compensará e manterá o total previsto (com impacto direto registado na variável MULTIPLICADOR_PROPRIO_DIA).
* **Situação Especial**: Se uma preparação agendada tiver de acontecer, mas o item atingiu a capacidade máxima em preparação, o agendamento espera na ITEM_QUEUE e entra em preparação assim que surgir espaço livre.

### 2.6. Métricas de Desempenho e Auditoria
* **Rácio de Desperdício**: Contador acumulado que regista a relação entre itens descartados e produzidos: (items_trashed / items_produced).
* **Tempo Total de Espera**: Somatório do tempo em minutos que as ordens não previstas passaram na ORDERS_QUEUE até serem respondidas (o valor ideal é 0).
* **Tempo Médio de Fila (Avg Queue Time)**: total queue time / orders.
* **Nível de Serviço (Service Level)**: orders fulfilled_immediately / total_orders.

### 2.7. Otimização da Base de Dados
* **Cálculo Assíncrono**: Os valores de PCT_EVENT e PCT_WEATHER são pré-calculados numa tabela
* **Periodicidade**: Atualização realizada numa rotina noturna (nightly).


### 2.8. Especificação da Página do Monitor de Produção (Tempo Real)
* **Modos de Visualização**: Permite alternar entre uma visão geral (com todos os Produtos de Preparação diferenciados por cores) ou uma visão focada num único Produto de Produção selecionado.
* **Estrutura de Visualização (7 Colunas da Esquerda para a Direita)**:
  1. FATURAS: Apresenta todas as faturas com uma nota descritiva indicando os Produtos de Produção incluídos. Esta é a única coluna que exibe todos os produtos da venda (sejam eles de produção ou não); as colunas seguintes tratam exclusivamente de itens de produção.
  2. ORDERS_QUEUE: Listagem dos itens pedidos que não foram antecipados pela previsão (prediction). Assim que um item sai da produção para responder a esta ordem, ela é transferida para a coluna ORDERS_ANSWERED.
  3. ORDERS ANSWERED (History): Histórico de pedidos atendidos. Se o item estivesse pronto na prateleira, o pedido entra diretamente aqui e o produto sai da prateleira. Cada registo armazena o respetivo tempo de espera (sendo 0 o valor ideal caso a previsão esteja correta).
  4. ITEM_QUEUE: Linha de espera para itens que aguardam a libertação de espaço na PREPARAÇÃO devido ao teto da capacidade máxima.
  5. ITEM_PREP: Itens em processamento durante o seu TEMPO_PREPARAÇÃO. Exibe no topo da coluna um sumário com o rácio de ocupação atual face ao máximo (no_item_atual / no_item_max) para cada tipo de item.
  6. SHELF: Itens totalmente preparados e disponíveis para entrega. 
  7. TRASH (History): Histórico detalhado contendo todos os itens que foram descartados e enviados para o lixo.


## 4. Estrtura de Dados
Produtos de Produção, vão ser represntados por tuples (string:NOME,Int:TEMPO_PRODUCAO,INT:TEMPO_PRATELEIRA,Int:MAX_CAPACITY)
  * Fries: Tempo Produção = 2 min (3 min total com buffer) | Tempo Prateleira = 10 min | Max Capacity = 24.
  * beef Burger: Tempo Produção = 4 min (5 min total com buffer) | Tempo Prateleira = 20 min | Max Capacity = 8.
  * Chicken Burger: Tempo Produção = 4 min (5 min total com buffer) | Tempo Prateleira = 20 min | Max Capacity = 8.
  * Fish Burger: Tempo Produção = 6 min (7 min total com buffer) | Tempo Prateleira = 15 min | Max Capacity = 6.
  * Vegan Burger: Tempo Produção = 6 min (7 min total com buffer) | Tempo Prateleira = 15 min | Max Capacity = 6.
  * Apple Pie: Tempo Produção = 10 min (11 min total com buffer) | Tempo Prateleira = 40 min | Max Capacity = 5.

as "Orders" (ou do Predictive Model, ou mandadas fazer diretamente, porque não estão no predictive model) uma class: [string:NOME,string:HORA_EMICAO,string:HORA_RECEBIDO,string:ESTADO], o HORA_RECEBIDO pode ser "" se a ORDER estiver na queue ainda, ESTADO pode ser: "ESPERA" ou "ENTREGUE"

os "Items" tambem são representados numa class: [string:NOME,string:HORA_PRONTO,string:HORA_PRAZO,string:HORA_ENTREGUE,string:ESTADO], HORA_ENTEGUE pode ser "" se ainda estiver na prateleira  sem ser atribuido a uma order, ou se for para o lixo, ou se tiver , ESTADO pode ser: "ESPERA","PREPARACAO","PRATELEIRA", "ENTREGUE", "LIXO"

cada uma das 7 colunas em Estrutura de Visualização (7 Colunas da Esquerda para a Direita) é representada por um array:

NOTA: A avaliaçao dos estados e transições é uma avaliaçao que ocorre a todos os minutos
1. (global)FATURAS: um array de arrays, em que cada um é o uma entry da base de dados daquele dia, estes arrays são inseridos no array de acordo com o relogio simulado, e vão para o fim do array, este array é so de oberservação, porque a funcao de parser ja pôs na ORDERS_QEUEU, todas as Orders do dia
2. (x6 -> um array para cada Prodduto de preparação) ORDERS_QUEUE: um array de estrturas da class "Orders". este array ja tem todas as "Orders", mas quando tempo_atual= fica com ESTADO="ESPERA".
3. (x6 -> um array para cada Prodduto de preparação) ORDERS_ANSWERD: um array de estrturas da class "Orders". vão para este array as  "Orders" que estão na ORDERS_QUEUE e aparece o Produto de Produção na SHELF para dar match
4. (x6 -> um array para cada Prodduto de preparação) ITEM_QUEUE: array de estrturas da class "Items". neste array so estão Itemscuja HORA_PRONTO="", HORA_PRAZO="", HORA_ENTREGUE="", ESTADO="ESPERA", estes items vem para este array quando o tamanho do array ITEM_PREP = MAX_CAPACITY desses PRoduto de PRodução. o sisema faz check a cada minuto para que qunado houver espaço este artigo passe para o array ITEM_PREP, e os campos HORA_PRONTO=atual+TEMPO_PREPARACAO, HORA_PRAZO=HORA_PRONTO+TEMPO_PRATELEIRA, HORA_ENTREGUE="", ESTADO="PREPARACAO" sejam calculados. caso o ITEM_PREP esteja no maximo neste array esntram os Items que são gerados naquele minuto pelo Predictive Model, ou os que são pedidos diretamente (não estao previstos no predctive Model)
5. (x6 -> um array para cada Prodduto de preparação) ITEM_PREP: array de estrturas da class "Items". os items entram nesta lista desde a ITEM_QUEUE ou os que são gerados naquele minuto pelo Predictive Model, ou os que são pedidos diretamente (não estao previstos no predctive Model). entram nesta lista X minutos antes da HORA_PRONTO (X = TEMPO_PREPARACAO+1), e assim que entram ja preenche os campos HORA_PRONTO=atual+TEMPO_PREPARACAO, HORA_PRAZO=HORA_PRONTO+TEMPO_PRATELEIRA, HORA_ENTREGUE="", ESTADO="PREPARACAO"
6. (x6 -> um array para cada Prodduto de preparação) SHELF: array de estrturas da class "Items". os items que estao no ITEM_PREP quando chega o minuto em que hora_atual=HORA_PRONTO, passam para este array e ESTADO="PRATELEIRA"
7. (x6 -> um array para cada Prodduto de preparação) TRASH: os items que estao em SHELF quando chega o minuto em que hora_atual=HORA_PRAZO, passam para este array e ESTADO="LIXO"

ACTION de atribuir um Item a uma Order: Um item da SHELF é atribuido as Orders da ORDERS_QEUEU, e a Order passa para ORDERS_ANSWERED, e este item fica com ESTADO="ENTREGUE" (e sai do array SHELF e não aperec em mais lado nenhum no formato Item porque ja vai apercer no formato Order em ORDERS_ANSWERED) 

## 5. Modelo de Simulação de Pedidos Reais
Um modelo baseado no dataset existente que vai ter um comportamento natural em relação ao datset, incluindo a ter em conta as horas de pico, dia da semana, eventos e weather.

O modelo gera as entries para aqeuele dia todo quando o utlizidar clica em "Começar o Dia"

Depois uma funçao de "parsing" percorre os pedidos do dia e faz um array (x6 -> um array para cada Prodduto de preparação) com  as Orders desse dia, cada uma para o respetivo Array (Nome=, HORA_EMITIDA=hora_da_fatura, Hora_ENTRGUE="", ESTADO="")

Depois vai estar a correr um clock simulado (1minuto = 2 segundos), e a cada minuto simulado é feita a avaliaçao as estrturas de dados reposnsaveis pelas actions no sistema


## 6. Atualização da Base de Dados
Durante a execução do dia apenas é preciso por e ir buscar dados a uma tabela que é a tabela do MULTPLICADOR_PROPRIO_DIA:
time_window,prod,nr_predicted_orders,nr_real_orders
11:00_11:09,fries,x,x
11:10_11:19,fries,x,x
...
23:50_23:59,fries,x,x
11:00_11:19,beef_burger,x,x
11:20_11:39,beef_burger,x,x
...
23:40_23:59,beef_burger,x,x
11:00_11:19,chicken_burger,x,x
...

é preciso inserir os dados no final de cada time_window para cada Produto de Produção com o numeoro de predicted orders e o numero de real orders (então é preciso uma variavel a contar esses valores durnate a execuçao para no fim de cada time_window colocar).depois quando for fazer a previsão do numero de Produtos de Produção X mintos antes da time_window, é preciso conusltar a tabela para calcular o valor de MULTPLICADOR_PROPRIO_DIA para aquele Produto de PRodução especifico

## 7. Modo de Utilização
A aplicaçao abre e apresenta a pagina inicial com uma tabela que prevê as orders de cada Produto de Produção para cada time_window respetiva a esse Produto De Produção para o proximo dia (o dia a seguir ao ultimo disponivel na base de dados). esta previsão é feita com a formula :
CALCULO(time_window, prod) = VALUE(time_window, prod) * PCT_DIFERENCIAÇÃO_EVENT(time_window, prod) * PCT_DIFERENCIAÇÃO_WEATHER(time_window, prod) * MULTIPLICADOR_MANUAL(global para o dia, global para todos os prod) * MULTIPLICADOR_PROPRIO_DIA (ultimo valor calculado - ha um novo a cada time_window,prod)

Os valor VALUE, PCT_DIFERECIAÇAO_EVENT, PCT_DIFERECIAÇAO_EVENT são calculados previamente (para cada Produto de produção em cada time_window), porque vão ser usados quando o algoritmo estiver a correr em tempo real. Esses valores são calculados assim que nessa pagina inicial o utilizador escolhe o valor para as variaves Event (None, Holiday, Small Special Event, Big Special Event) e Weather (Not Raining, Raining). E escolhe tambem o valor para MULTIPLICADOR_MANUAL. Quando o utilizador seleciona "Começar o dia", os valores para para VALUE, PCT_DIFERECIAÇAO_EVENT, PCT_DIFERECIAÇAO_EVENT e MULTIPLICADOR_MANUAL estão locked, e o calculo pode ser feito: PRE_CALCULO(time_window, prod)=VALUE(time_window, prod) * PCT_DIFERENCIAÇÃO_EVENT(time_window, prod) * PCT_DIFERENCIAÇÃO_WEATHER(time_window, prod) * MULTIPLICADOR_MANUAL * 1 pode ser calculado e guardado em cache para cada produto em cada time_window. 

Depois em tempo real assim que for hora de lançar cada uma das predictions a tempo do seu TEMPO_PREPARAÇãO para estar pronto na time_window correta, o calculo seguinte vai ser feito: CALCULO = PRE_CALCULO * MULTIPLICADOR_PROPRIO_DIA(ultimo valor calculado - ha um novo a cada time_window,prod)


A aplicação vai para a pagina  com a Estrutura de Visualização (7 Colunas da Esquerda para a Direita) e em tempo real (com um relogio a ir das 10:30 ate as 0:00, com 1minuto simulado = 2 segundos)corre o predictive model durante um dia, o Modelo de Simulação De Pedidos Reais corre antes de começar o dia é adicionada a base de dados ja o dia simulado.

Nesse momento o utilizidor é so um espetador e vê a Simulação e o predictive model a correr na Estrutura de Visualização (7 Colunas da Esquerda para a Direita) em tempo real.

Nesta fase ha uma camada no backend resposnsavel por gerir a relação entre as Orders do Simulador e as Orders mandadas fazer pelo Predictive Model em tempo real, respondendo aos pedidos diretamente se o produto de produção pedido estiver disponivel, fazer a order extra se o produto de produçao requeriod não estiver feito, e deitar ao lixo os produtos de produçao em prateliera quando acabar o prazo de TEMPO_PRATELEIRA

Quando o dia acaba é apresentada umapagina com as Metrics

Depois o utilizador volta a pagina innicial e escolhe os seus valores para PCT_DIFERECIAÇAO_EVENT, PCT_DIFERECIAÇAO_EVENT e MULTIPLICADOR_MANUAL, e pode começar o dia seguinte
