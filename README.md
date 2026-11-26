# Painel de Acidentes nas Rodovias Federais — PRF 2026

Projeto do CFO — Academia de Polícia Militar do Cabo Branco (APMCB) · Cadetes PM Saraiva, Fábio e Suelligton

## Sobre o projeto

Painel interativo para explorar acidentes nas rodovias federais brasileiras com indicadores, filtros, gráficos, mapa e análise de risco. A aplicação utiliza dados abertos da Polícia Rodoviária Federal (PRF), referentes ao período de janeiro a setembro de 2026. O objetivo é facilitar a consulta e a análise dos registros por localidade, período e características dos acidentes.

## Funcionalidades

- Página inicial com visão geral e indicadores principais.
- Subpáginas com detalhes e visualizações por indicador.
- Painel completo com gráficos, tabelas e mapa.
- Análise de risco pela Unidade Padrão de Severidade (UPS), incluindo trechos críticos.
- Filtros por UF, BR, município, período, causa, tipo, classificação, fase e clima.
- Modo escuro e modo apresentação.
- Download dos dados filtrados em CSV.

## Tecnologias

- Python
- Django
- Pandas
- Plotly
- Tailwind CSS
- Git
- Ambiente de desenvolvimento: Ubuntu (WSL), VS Code e GitHub Copilot

## Como rodar

Clone o repositório e entre na pasta do projeto:

```bash
git clone <URL_DO_REPOSITORIO>
cd <PASTA_DO_REPOSITORIO>
```

Crie e ative o ambiente virtual, instale as dependências, aplique as migrações e inicie o servidor:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Abra [http://localhost:8000](http://localhost:8000) no navegador.

## Estrutura de pastas

```text
projeto_novo/
├── config/                     # Configurações e rotas do projeto Django
│   ├── settings.py             # Configurações da aplicação e do banco local
│   ├── urls.py                 # Rotas principais
│   ├── asgi.py                 # Entrada ASGI
│   └── wsgi.py                 # Entrada WSGI
├── data/
│   └── base.csv                # Dados abertos da PRF usados pelo painel
├── eda/
│   └── inspecao.py             # Inspeção e análise exploratória dos dados
├── painel/                     # Aplicação Django do painel
│   ├── dados.py                # Leitura, limpeza, cache e cálculo dos indicadores
│   ├── views.py                # Páginas, filtros, gráficos e exportação CSV
│   ├── urls.py                 # Rotas da aplicação
│   ├── tests.py                # Testes automatizados
│   ├── templates/painel/       # Templates HTML das páginas
│   ├── static/painel/          # Arquivos estáticos, como o brasão
│   └── migrations/             # Migrações do banco de dados
├── manage.py                   # Comandos administrativos do Django
└── requirements.txt            # Dependências Python
```

## Indicadores

| KPI | Regra de cálculo |
|---|---|
| Acidentes | Contagem de linhas do conjunto filtrado; cada linha corresponde a um registro de acidente. |
| Mortos | Soma da coluna `mortos`. |
| Feridos graves | Soma da coluna `feridos_graves`. |
| Feridos leves | Soma da coluna `feridos_leves`. |
| Veículos | Soma da coluna `veiculos`. |
| Gravidade | Mortos ÷ acidentes × 100 (mortos por 100 acidentes). Se não houver acidentes, o resultado é zero. |
| UPS | Soma dos pesos por acidente: **1** sem vítimas, **5** com vítimas feridas e **13** com vítimas fatais. |

## Fonte dos dados

**PRF – Dados Abertos**, base de acidentes em rodovias federais (Datatran 2026), de janeiro a setembro de 2026. O arquivo utilizado pelo projeto é `data/base.csv`.
