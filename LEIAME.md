# Painel de acidentes em rodovias federais

Aplicação Django para explorar os dados abertos da PRF sobre acidentes em rodovias
federais. A página inicial apresenta os indicadores; as páginas de cada indicador
detalham sua evolução e distribuição; `/painel/` reúne gráficos, filtros e mapas.

## Instalação e execução

Requer Python instalado. Na raiz do projeto, crie e ative o ambiente virtual e
instale as dependências:

```bash
python3 -m venv venv
source venv/bin/activate
venv/bin/python -m pip install -r requirements.txt
```

Confirme a configuração e inicie o servidor local:

```bash
venv/bin/python manage.py check
venv/bin/python manage.py runserver
```

Abra `http://127.0.0.1:8000/`. Para rodar os testes:

```bash
venv/bin/python manage.py test
```

## Indicadores (KPIs)

- **Acidentes:** quantidade de linhas; cada linha representa um acidente.
- **Mortos:** soma da coluna `mortos`.
- **Feridos graves:** soma da coluna `feridos_graves`.
- **Feridos leves:** soma da coluna `feridos_leves`.
- **Veículos:** soma da coluna `veiculos`.
- **Gravidade:** `mortos / acidentes * 100`, exibido com duas casas decimais.
  Quando não há acidentes, o indicador retorna zero.

## Atualização da base

1. Baixe a versão desejada dos dados abertos de acidentes (Datatran) no site da PRF.
2. Salve ou substitua o arquivo em `data/base.csv`, mantendo o CSV separado por
   ponto e vírgula e a codificação usada no arquivo original.
3. Na próxima carga, `painel/dados.py` detecta a alteração pelo tamanho e data de
   modificação do arquivo e refaz automaticamente `data/.cache.pkl`.

Não é necessário editar nem apagar manualmente o cache.

## Arquivos do projeto

### Dados e análise

- `data/base.csv`: arquivo bruto do Datatran usado pelo painel.
- `data/.cache.pkl`: cache dos dados limpos, criado automaticamente.
- `eda/inspecao.py`: análise exploratória do CSV (dimensões, colunas, nulos,
  frequências, estatísticas e amostra).
- `requirements.txt`: dependências Python do projeto.
- `LEIAME.md`: instruções de instalação, indicadores e atualização da base.

### Projeto Django (`config/`)

- `config/settings.py`: configurações do Django, aplicações, templates e hosts.
- `config/urls.py`: inclui as rotas do painel na raiz do site e registra o admin.
- `config/asgi.py` e `config/wsgi.py`: pontos de entrada ASGI e WSGI para servidores.
- `config/__init__.py`: identifica `config` como pacote Python.

### Aplicação do painel (`painel/`)

- `painel/dados.py`: leitura, limpeza, cache da base e cálculo dos KPIs.
- `painel/views.py`: filtros, agregações, gráficos, páginas e exportação CSV.
- `painel/urls.py`: rotas da página inicial, indicadores, painel completo e recursos.
- `painel/tests.py`: testes de limpeza, KPIs, mapas e respostas das páginas.
- `painel/templates/painel/base.html`: cabeçalho, navegação, filtros e rodapé comuns.
- `painel/templates/painel/home.html`: cartões de KPIs e gráfico da página inicial.
- `painel/templates/painel/indicador.html`: detalhes de um indicador.
- `painel/templates/painel/painel.html`: painel completo, gráficos e tabelas.
- `painel/static/painel/brasao.png`: brasão exibido no cabeçalho.
- `painel/apps.py`: configuração da aplicação Django `painel`.
- `painel/models.py`: modelos de banco de dados (o painel usa a base CSV, sem modelos
  próprios atualmente).
- `painel/admin.py`: configuração de registros no admin (sem registros próprios
  atualmente).
- `painel/__init__.py` e `painel/migrations/__init__.py`: identificam os pacotes
  Python da aplicação e das migrações.

### Comandos

- `manage.py`: utilitário de linha de comando do Django para executar o servidor,
  verificações, testes e outras tarefas administrativas.
- `db.sqlite3`: banco local usado pelo Django para componentes internos, como sessões
  e administração; os acidentes são lidos de `data/base.csv`.
