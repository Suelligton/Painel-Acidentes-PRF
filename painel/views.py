from io import StringIO

import pandas as pd
import plotly.express as px
from django.http import HttpResponse
from django.shortcuts import render
from plotly.offline import get_plotlyjs, plot

from .dados import INDICADORES, MESES_NOME, calcular_kpi, carregar_dados


CORES_PMPB = {
    "vermelho": "#C8102E",
    "vermelho_escuro": "#7A0C14",
    "preto": "#1C1C1C",
    "dourado": "#C9A227",
    "cinza": "#78716C",
}

CORES_CLASSIFICACAO = {
    "Com Vítimas Fatais": CORES_PMPB["vermelho_escuro"],
    "Com Vítimas Feridas": CORES_PMPB["dourado"],
    "Sem Vítimas": CORES_PMPB["cinza"],
    "NÃO INFORMADO": CORES_PMPB["preto"],
}

DIAS_SEMANA = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]

FILTROS_PARA_COLUNAS = {
    "causa": "causa_acidente",
    "tipo": "tipo_acidente",
    "classificacao": "classificacao_acidente",
    "fase": "fase_dia",
    "clima": "condicao_metereologica",
}


def _valores_texto(df, coluna):
    return sorted(df[coluna].dropna().astype(str).unique().tolist(), key=str.casefold)


def _brs(df):
    return [str(int(valor)) for valor in sorted(df["br"].dropna().unique())]


def _periodos(df):
    datas = df["data"].dropna()
    return sorted(datas.dt.strftime("%Y-%m").unique().tolist())


def _opcoes_dependentes(df):
    ufs = _valores_texto(df, "uf")
    brs_por_uf = {"": _brs(df)}
    municipios_por_uf = {"": _valores_texto(df, "municipio")}

    for uf in ufs:
        dados_uf = df.loc[df["uf"].astype(str) == uf]
        brs_por_uf[uf] = _brs(dados_uf)
        municipios_por_uf[uf] = _valores_texto(dados_uf, "municipio")

    return ufs, brs_por_uf, municipios_por_uf


def ler_filtros(request):
    """Lê os filtros da URL e descarta valores que não existem na base."""
    df = carregar_dados()
    ufs, brs_por_uf, municipios_por_uf = _opcoes_dependentes(df)
    periodos = _periodos(df)
    filtros = {
        nome: request.GET.get(nome, "").strip()
        for nome in (
            "uf",
            "br",
            "municipio",
            "mes_ini",
            "mes_fim",
            "causa",
            "tipo",
            "classificacao",
            "fase",
            "clima",
        )
    }

    # Cada filtro textual só é mantido se corresponder a uma opção real.
    if filtros["uf"] not in ufs:
        filtros["uf"] = ""

    # BR e município dependem da UF válida; sem UF, a lista inclui todos.
    chave_uf = filtros["uf"]
    if filtros["br"] not in brs_por_uf[chave_uf]:
        filtros["br"] = ""
    if filtros["municipio"] not in municipios_por_uf[chave_uf]:
        filtros["municipio"] = ""

    # Os meses usam o formato ano-mês para ordenar corretamente entre anos.
    for nome in ("mes_ini", "mes_fim"):
        if filtros[nome] not in periodos:
            filtros[nome] = ""
    if filtros["mes_ini"] and filtros["mes_fim"] and filtros["mes_ini"] > filtros["mes_fim"]:
        filtros["mes_ini"] = ""
        filtros["mes_fim"] = ""

    for nome, coluna in FILTROS_PARA_COLUNAS.items():
        if filtros[nome] not in _valores_texto(df, coluna):
            filtros[nome] = ""

    return filtros


def aplicar_filtros(df, filtros):
    """Retorna uma cópia com todos os filtros válidos aplicados."""
    mascara = pd.Series(True, index=df.index)

    for nome, coluna in (
        ("uf", "uf"),
        ("municipio", "municipio"),
        ("causa", "causa_acidente"),
        ("tipo", "tipo_acidente"),
        ("classificacao", "classificacao_acidente"),
        ("fase", "fase_dia"),
        ("clima", "condicao_metereologica"),
    ):
        valor = filtros.get(nome, "")
        if valor:
            mascara &= df[coluna].astype("string") == valor

    if filtros.get("br"):
        mascara &= df["br"].astype("string") == filtros["br"]

    periodo = df["data"].dt.strftime("%Y-%m").fillna("")
    if filtros.get("mes_ini"):
        mascara &= periodo >= filtros["mes_ini"]
    if filtros.get("mes_fim"):
        mascara &= periodo <= filtros["mes_fim"]

    return df.loc[mascara].copy()


def _formatar_inteiro(valor):
    return f"{int(valor):,}".replace(",", ".")


def _rotulo_periodo(periodo):
    ano, numero_mes = periodo.split("-")
    return f"{MESES_NOME[int(numero_mes)]}/{ano}"


def _aplicar_tema(figura):
    figura.update_layout(
        template="plotly_white",
        font={"family": "Inter, sans-serif", "color": CORES_PMPB["preto"]},
        colorway=[
            CORES_PMPB["vermelho"],
            CORES_PMPB["vermelho_escuro"],
            CORES_PMPB["dourado"],
            CORES_PMPB["cinza"],
            CORES_PMPB["preto"],
        ],
        separators=",.",
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin={"l": 24, "r": 24, "t": 55, "b": 35},
    )
    return figura


def _figura_div(figura):
    return plot(
        figura,
        output_type="div",
        include_plotlyjs=False,
        config={"displaylogo": False},
    )


def _grafico_mensal(df, periodos):
    mensal = (
        df.assign(periodo=df["data"].dt.strftime("%Y-%m"))
        .groupby("periodo")
        .agg(acidentes=("id", "size"), mortos=("mortos", "sum"))
        .reindex(periodos, fill_value=0)
        .rename_axis("periodo")
        .reset_index()
    )
    longo = mensal.melt(
        id_vars="periodo",
        value_vars=["acidentes", "mortos"],
        var_name="indicador",
        value_name="valor",
    )
    longo["indicador"] = longo["indicador"].map(
        {"acidentes": "Acidentes", "mortos": "Mortos"}
    )
    longo["mes"] = longo["periodo"].map(_rotulo_periodo)
    rotulos = [_rotulo_periodo(periodo) for periodo in periodos]

    figura = px.line(
        longo,
        x="mes",
        y="valor",
        color="indicador",
        facet_col="indicador",
        facet_col_wrap=1,
        markers=True,
        category_orders={
            "indicador": ["Acidentes", "Mortos"],
            "mes": rotulos,
        },
        color_discrete_map={
            "Acidentes": CORES_PMPB["vermelho"],
            "Mortos": CORES_PMPB["vermelho_escuro"],
        },
        title="Evolução mensal de acidentes e mortos",
        template="plotly_white",
    )
    figura.update_yaxes(matches=None, rangemode="tozero", title_text="")
    figura.update_xaxes(title_text="", tickangle=-25)
    figura.for_each_annotation(
        lambda anotacao: anotacao.update(text=anotacao.text.split("=")[-1])
    )
    figura.update_layout(showlegend=False, height=610)
    return _aplicar_tema(figura)


def _figura_barras(contagens, titulo, cor):
    contagens = (
        contagens.sort_values(ascending=True)
        .rename_axis("categoria")
        .reset_index(name="acidentes")
    )
    figura = px.bar(
        contagens,
        x="acidentes",
        y="categoria",
        orientation="h",
        text="acidentes",
        title=titulo,
        color_discrete_sequence=[cor or CORES_PMPB["vermelho"]],
        template="plotly_white",
    )
    figura.update_traces(
        texttemplate="%{x:,.0f}",
        textposition="inside",
        textfont_color="white",
        cliponaxis=False,
    )
    figura.update_layout(
        xaxis_title="Acidentes",
        yaxis_title="",
        margin={"l": 24, "r": 25, "t": 55, "b": 30},
    )
    return _aplicar_tema(figura)


def _grafico_barras(df, coluna, titulo, limite=None, cor=None):
    contagens = df[coluna].value_counts()
    if limite is not None:
        contagens = contagens.head(limite)
    return _figura_barras(
        contagens,
        titulo,
        cor or CORES_PMPB["vermelho"],
    )


def _grafico_calor(df):
    tabela = (
        df.groupby(["dia_semana", "hora"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=DIAS_SEMANA, columns=range(24), fill_value=0)
    )
    figura = px.imshow(
        tabela,
        x=[f"{hora:02d}" for hora in range(24)],
        y=DIAS_SEMANA,
        aspect="auto",
        text_auto=True,
        labels={"x": "Hora do dia", "y": "Dia da semana", "color": "Acidentes"},
        color_continuous_scale=[
            [0, "#F5F5F4"],
            [0.5, CORES_PMPB["dourado"]],
            [1, CORES_PMPB["vermelho"]],
        ],
        title="Acidentes por dia da semana e hora",
        template="plotly_white",
    )
    figura.update_xaxes(title_text="Hora do dia")
    figura.update_yaxes(title_text="Dia da semana")
    return _aplicar_tema(figura)


def _grafico_rosca(df, coluna, titulo):
    contagens = (
        df[coluna]
        .value_counts()
        .rename_axis("categoria")
        .reset_index(name="acidentes")
    )
    figura = px.pie(
        contagens,
        names="categoria",
        values="acidentes",
        hole=0.58,
        title=titulo,
        color_discrete_sequence=[
            CORES_PMPB["vermelho"],
            CORES_PMPB["vermelho_escuro"],
            CORES_PMPB["dourado"],
            CORES_PMPB["cinza"],
            CORES_PMPB["preto"],
        ],
        template="plotly_white",
    )
    figura.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="%{label}<br>Acidentes: %{value:,.0f}<extra></extra>",
    )
    return _aplicar_tema(figura)


def _grafico_mapa(df):
    pontos = df.dropna(subset=["latitude", "longitude"])
    titulo = "Localização dos acidentes"
    if len(pontos) > 5000:
        pontos = pontos.sample(n=5000, random_state=1)
        titulo += " — amostra de 5.000 pontos"
    if pontos.empty:
        return None

    figura = px.scatter_map(
        pontos,
        lat="latitude",
        lon="longitude",
        color="classificacao_acidente",
        color_discrete_map=CORES_CLASSIFICACAO,
        hover_name="municipio",
        hover_data={
            "id": True,
            "uf": True,
            "br": True,
            "km": ":.1f",
            "mortos": True,
            "latitude": False,
            "longitude": False,
        },
        map_style="open-street-map",
        center={"lat": -14.2, "lon": -51.9},
        zoom=3,
        opacity=0.7,
        title=titulo,
    )
    figura.update_traces(marker={"size": 8})
    figura.update_layout(height=600, margin={"l": 0, "r": 0, "t": 55, "b": 0})
    return _aplicar_tema(figura)


def _preparar_tabelas(df):
    trechos = (
        df.loc[df["trecho"] != "NÃO INFORMADO"]
        .groupby("trecho")
        .agg(acidentes=("id", "size"), mortos=("mortos", "sum"))
        .sort_values(["acidentes", "mortos"], ascending=False)
        .head(10)
        .reset_index()
    )
    municipios = (
        df.groupby(["municipio", "uf"])
        .agg(acidentes=("id", "size"), mortos=("mortos", "sum"))
        .sort_values(["acidentes", "mortos"], ascending=False)
        .head(10)
        .reset_index()
    )

    return (
        [
            {
                "trecho": linha.trecho,
                "acidentes": _formatar_inteiro(linha.acidentes),
                "mortos": _formatar_inteiro(linha.mortos),
            }
            for linha in trechos.itertuples(index=False)
        ],
        [
            {
                "municipio": linha.municipio,
                "uf": linha.uf,
                "acidentes": _formatar_inteiro(linha.acidentes),
                "mortos": _formatar_inteiro(linha.mortos),
            }
            for linha in municipios.itertuples(index=False)
        ],
    )


def _gerar_graficos(df, periodos, filtros):
    mapa = _grafico_mapa(df)
    if filtros["uf"]:
        contagens_ranking = df["br"].dropna().astype(int).value_counts()
        contagens_ranking.index = [
            f"BR-{valor}" for valor in contagens_ranking.index
        ]
        titulo_ranking = f"Ranking de acidentes por BR · {filtros['uf']}"
    else:
        contagens_ranking = df["uf"].value_counts()
        titulo_ranking = "Ranking de acidentes por UF"

    return {
        "mensal": _figura_div(_grafico_mensal(df, periodos)),
        "causas": _figura_div(
            _grafico_barras(
                df,
                "causa_acidente",
                "10 principais causas de acidentes",
                limite=10,
                cor=CORES_PMPB["vermelho"],
            )
        ),
        "tipos": _figura_div(
            _grafico_barras(
                df,
                "tipo_acidente",
                "Acidentes por tipo",
                cor=CORES_PMPB["vermelho_escuro"],
            )
        ),
        "ranking": _figura_div(
            _figura_barras(
                contagens_ranking,
                titulo_ranking,
                CORES_PMPB["vermelho_escuro"],
            )
        ),
        "calor": _figura_div(_grafico_calor(df)),
        "fase": _figura_div(_grafico_rosca(df, "fase_dia", "Acidentes por fase do dia")),
        "clima": _figura_div(
            _grafico_rosca(
                df,
                "condicao_metereologica",
                "Acidentes por condição meteorológica",
            )
        ),
        "mapa": _figura_div(mapa) if mapa is not None else None,
    }


def painel(request):
    df = carregar_dados()
    filtros = ler_filtros(request)
    filtrado = aplicar_filtros(df, filtros)
    todos_periodos = _periodos(df)
    periodos_grafico = [
        periodo
        for periodo in todos_periodos
        if (not filtros["mes_ini"] or periodo >= filtros["mes_ini"])
        and (not filtros["mes_fim"] or periodo <= filtros["mes_fim"])
    ]

    kpis = []
    for chave, indicador in INDICADORES.items():
        valor = calcular_kpi(filtrado, chave)
        if indicador["tipo"] == "razao":
            valor_formatado = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            valor_formatado = _formatar_inteiro(valor)
        kpis.append(
            {
                "nome": indicador["nome"],
                "descricao": indicador["descricao"],
                "valor": valor_formatado,
            }
        )

    if filtrado.empty:
        graficos = {}
        mensagem_sem_registros = "Sem registros para os filtros escolhidos"
        tabela_trechos, tabela_municipios = [], []
    else:
        graficos = _gerar_graficos(filtrado, periodos_grafico, filtros)
        mensagem_sem_registros = ""
        tabela_trechos, tabela_municipios = _preparar_tabelas(filtrado)

    ufs, brs_por_uf, municipios_por_uf = _opcoes_dependentes(df)
    chave_uf = filtros["uf"]
    return render(
        request,
        "painel/painel.html",
        {
            "filtros": filtros,
            "querystring": request.GET.urlencode(),
            "graficos": graficos,
            "mensagem_sem_registros": mensagem_sem_registros,
            "kpis": kpis,
            "tabela_trechos": tabela_trechos,
            "tabela_municipios": tabela_municipios,
            "ufs": ufs,
            "brs": brs_por_uf[chave_uf],
            "municipios": municipios_por_uf[chave_uf],
            "brs_por_uf": brs_por_uf,
            "municipios_por_uf": municipios_por_uf,
            "meses": [
                {"valor": periodo, "rotulo": _rotulo_periodo(periodo)}
                for periodo in todos_periodos
            ],
            "causas": _valores_texto(df, "causa_acidente"),
            "tipos": _valores_texto(df, "tipo_acidente"),
            "classificacoes": _valores_texto(df, "classificacao_acidente"),
            "fases": _valores_texto(df, "fase_dia"),
            "climas": _valores_texto(df, "condicao_metereologica"),
            "total_filtrado": _formatar_inteiro(len(filtrado)),
        },
    )


def exportar_csv(request):
    df = aplicar_filtros(carregar_dados(), ler_filtros(request))
    arquivo = StringIO()
    df.to_csv(arquivo, index=False, sep=";", decimal=",")
    resposta = HttpResponse(
        "\ufeff" + arquivo.getvalue(),
        content_type="text/csv; charset=utf-8",
    )
    resposta["Content-Disposition"] = 'attachment; filename="acidentes_filtrados.csv"'
    return resposta


def plotly_js(request):
    return HttpResponse(get_plotlyjs(), content_type="application/javascript")
