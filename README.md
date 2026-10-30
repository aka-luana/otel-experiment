# otel-experiment

Um laboratório local para **ver OpenTelemetry funcionando na prática**: três microsserviços em Python que chamam uns aos outros, um Collector no meio e, do outro lado, ferramentas para olhar **traces**, **métricas** e **logs**, tudo subindo com um único `docker compose up`.

- [O que é OpenTelemetry?](#o-que-é-opentelemetry)
- [O problema do vendor lock-in](#o-problema-do-vendor-lock-in)
- [O que é (e o que faz) o Collector](#o-que-é-e-o-que-faz-o-collector)
- [Arquitetura do experimento](#arquitetura-do-experimento)
- [Como subir](#como-subir)
- [Como testar e se achar nas ferramentas](#como-testar-e-se-achar-nas-ferramentas)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Como o código está instrumentado](#como-o-código-está-instrumentado)
- [Parar e limpar](#parar-e-limpar)
- [Problemas comuns](#problemas-comuns)

---

## O que é OpenTelemetry?

Quando um sistema tem vários serviços, descobrir *"por que ficou lento?"* ou *"onde está dando erro?"* vira um dasafio. Para isso, os serviços precisam emitir **telemetria**, que são dados sobre o que estão fazendo. Existem três tipos, chamados de **pilares da observabilidade**:

| Pilar | Pergunta que responde | Exemplo |
|---|---|---|
| **Traces** | "Por onde essa requisição passou e quanto tempo gastou em cada lugar?" | A requisição entrou no serviço A, foi para o B, depois para o C, e o C demorou 800 ms. |
| **Métricas** | "Como o sistema está se comportando, em números, ao longo do tempo?" | 120 requisições por segundo, 3% de erro, latência p95 de 400 ms. |
| **Logs** | "O que exatamente aconteceu naquele momento?" | `app-c falhou: falha simulada no app-c` |

**OpenTelemetry (OTel)** é um projeto open source, que define **como gerar, formatar e transportar** esses três tipos de dados. Ele oferece:

- **APIs e SDKs** para várias linguagens (Python, Java, Go, JS, .NET...), que você usa dentro do seu código.
- **OTLP**, um protocolo único para enviar telemetria.
- **O Collector**, um programa que recebe, processa e encaminha a telemetria.

O OpenTelemetry **não armazena nem mostra** nada. Ele cuida só de *produzir e transportar* os dados. Quem guarda e desenha os gráficos são outras ferramentas (Jaeger, Prometheus, Grafana etc.), e é aí que ele ajuda.

## O problema do vendor lock-in

Antes do OpenTelemetry, cada ferramenta de monitoramento tinha o seu próprio SDK, o seu próprio formato e o seu próprio agente. Se você instrumentava o código para a ferramenta X, esse código ficava **amarrado** à ferramenta X.

```
 SEM OpenTelemetry                         COM OpenTelemetry

 seu código ──► SDK da ferramenta X        seu código ──► SDK OpenTelemetry ──► (OTLP)
                                                                                  │
 Trocar para a ferramenta Y?                                                      ▼
 → reescrever a instrumentação              Trocar de ferramenta?            Collector ──► X, Y ou Z
   em todos os serviços.                    → mudar uma configuração no Collector.
```

Isso é o **vendor lock-in**: você fica preso a um fornecedor porque sair custa caro, já que seria preciso mexer em todos os serviços. Com o OpenTelemetry, o código é instrumentado **uma vez**, num padrão neutro. Escolher, trocar ou combinar ferramentas passa a ser uma decisão de infraestrutura, e não de código.

Neste experimento você pode ver isso na prática: as aplicações **não sabem** que o Jaeger, o Prometheus ou o Loki existem. Elas só falam OTLP com o Collector.

## O que é (e o que faz) o Collector

Pense no Collector como **uma central de triagem dos Correios**:

- as aplicações entregam suas "encomendas" (telemetria) num único endereço;
- a central confere, agrupa e etiqueta;
- depois envia cada encomenda ao destino certo.

Tecnicamente, ele é um pipeline com três tipos de peça:

```
  receivers          processors            exporters
  (por onde entra)   (o que se faz no meio)  (para onde vai)

  ┌──────────┐      ┌──────────────┐      ┌──────────────┐
  │   otlp   │ ───► │    batch     │ ───► │ jaeger, ...  │
  └──────────┘      └──────────────┘      └──────────────┘
```

- **Receivers:** recebem dados. Aqui, OTLP por gRPC (porta 4317) e HTTP (porta 4318).
- **Processors:** transformam ou organizam. Aqui usamos o `batch`, que agrupa dados em lotes para enviar de forma mais eficiente. Em outros cenários, poderiam filtrar, remover dados sensíveis ou amostrar.
- **Exporters:** enviam para os destinos. Aqui, cada sinal vai para uma ferramenta diferente.

Por que usar um Collector em vez de a aplicação enviar direto para os backends?

- **Desacoplamento:** trocar de backend não exige mexer nas aplicações.
- **Um ponto só para configurar:** destino, filtros, tentativas de reenvio, tudo num único arquivo.
- **Menos peso nas aplicações:** elas só entregam ao Collector, e ele lida com as falhas de rede dos backends.

A configuração inteira do nosso Collector está em [`otel-collector/otel-collector-config.yaml`](otel-collector/otel-collector-config.yaml) e tem menos de 40 linhas.

## Arquitetura do experimento

```
                    GET /work
 você (curl) ──────────────────► app-a ───► app-b ───► app-c
                                   │          │          │
                                   └──────────┼──────────┘
                                              │  OTLP (gRPC 4317)
                                              ▼
                                    ┌──────────────────┐
                                    │  OTel Collector  │  (processor: batch)
                                    └─┬──────┬───────┬─┘
                                traces│ métr.│  logs │
                                      ▼      ▼       ▼
                                  Jaeger  Prometheus  Loki
                                      └──────┼───────┘
                                          Grafana
```

| Componente | Função | Endereço |
|---|---|---|
| `app-a` | Entrada da cadeia. Chama o `app-b`. | http://localhost:8001 |
| `app-b` | Meio da cadeia. Chama o `app-c`. | (só na rede interna) |
| `app-c` | Fim da cadeia. Pode falhar de propósito. | (só na rede interna) |
| **OTel Collector** | Recebe OTLP e distribui. | `localhost:4317` (gRPC), `localhost:4318` (HTTP) |
| **Jaeger** | Visualização de **traces** | http://localhost:16686 |
| **Prometheus** | Armazena e consulta **métricas** | http://localhost:9090 |
| **Loki** | Armazena **logs** | http://localhost:3100 (API) |
| **Grafana** | Painel único para consultar os três | http://localhost:3000 |

Uma requisição a `app-a` atravessa os três serviços e gera **um único trace** com todos eles. Isso é possível graças à **propagação de contexto**: cada chamada HTTP leva o cabeçalho padrão `traceparent`, que carrega o ID do trace, e o serviço seguinte continua o mesmo trace.

## Como subir

**Pré-requisitos:** [Docker](https://docs.docker.com/get-docker/) com Docker Compose.

```bash
git clone <url-do-repositorio>
cd otel-experiment
docker compose up -d --build
docker compose ps
```

Na primeira vez, o build demora alguns minutos. Todos os 8 serviços devem aparecer como `running`.

Para confirmar que o Collector subiu bem:

```bash
docker compose logs otel-collector --tail=5
# procure por: "Everything is ready. Begin running and processing data."
```

> O Grafana está com acesso anônimo de administrador (`GF_AUTH_ANONYMOUS_*`), então não pede login. Isso é conveniente para um laboratório local e **não deve ser usado em produção**.

## Como testar e se achar nas ferramentas

### 1. Gere tráfego

```bash
curl localhost:8001/work
```

Resposta (aninhada, mostrando a cadeia inteira):

```json
{"service":"app-a","next":{"service":"app-b","next":{"service":"app-c","latency_ms":165}}}
```

Para gerar mais volume e ter gráficos mais interessantes:

```bash
for i in $(seq 1 50); do curl -s -o /dev/null -w "%{http_code} " localhost:8001/work; done; echo
```

Aguarde uns 15 segundos. As métricas são enviadas a cada 5 s e o Prometheus raspa o Collector a cada 15 s.

### 2. Traces: Jaeger (http://localhost:16686)

1. Em **Service**, escolha `app-a`.
2. Clique em **Find Traces**.
3. Abra um trace. Você verá os spans dos três serviços em cascata: `app-a → app-b → app-c`.

O que procurar:
- Qual barra ocupa mais tempo? (normalmente o `app-c`, que dorme até 300 ms.)
- Os spans `GET /work http send` são ruído interno do servidor ASGI, e não erros.

### 3. Métricas: Grafana → Explore → Prometheus

Abra http://localhost:3000, vá em **Explore** (ícone de bússola), escolha o data source **Prometheus** e teste:

```promql
# Quantas vezes cada serviço foi chamado (contador próprio de cada app)
app_a_work_total
app_b_work_total
app_c_work_total

# Requisições por segundo, por serviço (métrica automática do FastAPI)
sum by (exported_job) (rate(http_server_duration_milliseconds_count[2m]))

# Latência p95 por serviço
histogram_quantile(0.95, sum by (le, exported_job) (rate(http_server_duration_milliseconds_bucket[2m])))
```

> `exported_job` é o `service.name` do OpenTelemetry. O label `job` puro é do Prometheus e sempre vale `otel-collector`.

### 4. Logs: Grafana → Explore → Loki

Escolha o data source **Loki** e teste:

```logql
# Todos os logs das três apps
{service_name=~"app-a|app-b|app-c"}

# Só os do app-c
{service_name="app-c"}

# Só os de nível erro
{service_name=~"app-a|app-b|app-c"} | detected_level="error"
```

### 5. Ligando os pilares: do log ao trace

Esse é o ganho de usar OpenTelemetry. Todo log emitido durante uma requisição carrega o `trace_id` dela.

1. No Loki, clique em uma linha de log para expandi-la.
2. Copie o valor de `trace_id`.
3. No Jaeger, cole esse ID no campo de busca por **Trace ID**.

Você chega no trace exato da requisição que gerou aquele log.

### 6. Enviando telemetria "na mão" (sem as apps)

Dá para falar com o Collector direto, sem usar as aplicações. Isso mostra que OTLP é só HTTP com JSON. Exemplo com uma métrica:

```bash
curl -X POST localhost:4318/v1/metrics -H 'Content-Type: application/json' -d '{
  "resourceMetrics": [{
    "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "teste-manual"}}]},
    "scopeMetrics": [{"metrics": [{
      "name": "teste_gauge",
      "gauge": {"dataPoints": [{"timeUnixNano": "'"$(date +%s)"'000000000", "asDouble": 42}]}
    }]}]
  }]
}'
```

A resposta esperada é `{"partialSuccess":{}}`. Em seguida, consulte `teste_gauge` no Prometheus.

## Estrutura do projeto

```
otel-experiment/
├── docker-compose.yml                 # orquestra os 8 serviços
├── app-a/ app-b/ app-c/               # microsserviços FastAPI
│   ├── main.py                        #   endpoint /work e lógica de cada serviço
│   ├── telemetry.py                   #   configuração do OpenTelemetry SDK
│   ├── requirements.txt
│   └── Dockerfile
├── otel-collector/
│   └── otel-collector-config.yaml     # receivers → processors → exporters
├── prometheus/
│   └── prometheus.yml                 # raspa as métricas expostas pelo Collector
└── grafana/provisioning/datasources/
    └── datasources.yml                # conecta Grafana a Prometheus, Loki e Jaeger
```

## Como o código está instrumentado

Todo o setup do OpenTelemetry está em [`app-a/telemetry.py`](app-a/telemetry.py) (e nas cópias idênticas de `app-b` e `app-c`). Em resumo:

- **Um provider por sinal** (`TracerProvider`, `MeterProvider`, `LoggerProvider`), cada um com um exporter OTLP apontando para o Collector.
- **Auto-instrumentação:** `FastAPIInstrumentor` cria um span para cada requisição recebida, e `HTTPXClientInstrumentor` cria um span para cada chamada feita e injeta o `traceparent`. É isso que costura o trace entre os serviços sem nenhum código de propagação.
- **Logs:** um `LoggingHandler` liga o módulo `logging` padrão do Python ao OpenTelemetry. Basta usar `logger.info(...)` como sempre, e o `trace_id` é anexado automaticamente.
- **Instrumentação manual:** cada app cria seu contador (`app_a.work`, etc.) com `meter.create_counter(...)`.
- **Configuração por ambiente:** o nome do serviço e o endereço do Collector vêm de `OTEL_SERVICE_NAME` e `OTEL_EXPORTER_OTLP_ENDPOINT`, definidos no `docker-compose.yml`. O mesmo código roda nos três serviços.

## Parar e limpar

```bash
docker compose down        # para e remove os containers
docker compose down -v     # idem, e apaga também os volumes
```

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Collector reinicia em loop | Erro de sintaxe no `otel-collector-config.yaml` | `docker compose logs otel-collector` mostra a chave inválida |
| Grafana → Jaeger: `404 Not Found` | Versões novas do Jaeger removeram a API antiga `/api/services`, que o Grafana usa | Manter a imagem fixada em `jaegertracing/jaeger:2.10.0`, como está no compose |
| Métrica não aparece no Prometheus | O scrape é a cada 15 s | Espere e confira http://localhost:9090/targets (o target `otel-collector` deve estar **UP**) |
| Logs não aparecem no Loki | A query usa o label errado | Use `service_name` (e não `job` nem `app`) |
| `address already in use` ao subir | Alguma porta (3000, 4317, 8001...) já está ocupada no seu computador | Feche o processo que a usa ou mude o mapeamento de portas no compose |
| Serviço sem dados no Jaeger | Variável do exporter errada ou Collector fora do ar | Confira `OTEL_EXPORTER_OTLP_ENDPOINT` no compose e `docker compose ps` |

## Versões usadas

As versões são fixadas de propósito, porque pacotes do OpenTelemetry precisam combinar entre si e imagens `latest` podem mudar sem aviso.

- OTel Collector (contrib): `0.141.0`
- Jaeger: `2.10.0`
- Loki: `3.4.2`
- OpenTelemetry Python SDK: `1.42.1` (instrumentações `0.63b1`)
- Prometheus e Grafana: `latest`
