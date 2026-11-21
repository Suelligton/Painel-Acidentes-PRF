import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from django.http import HttpResponseBadRequest
from django.shortcuts import render

from .dados import INDICADORES, calcular_kpi, carregar_dados


DIAS_SEMANA = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]
MESES = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]
CORES = ["#173b57", "#08a88a", "#f2a541", "#e36a63", "#6c79c8", "#50a3c2"]


def _formatar_inteiro(valor):
    return f"{int(valor):,}".replace(",", ".")


def _rotulo_mes(mes):
    ano, numero = mes.split("-")
    return f"{MESES[int(numero) - 1][:3].capitalize()}/{ano}"


def _validar_opcao(valor, opcoes, nome):
    if valor and valor not in opcoes:
        return HttpResponseBadRequest(f"Valor inválido para o filtro {nome}.")
    return None


def _configurar_figura(figura, altura=370):
    figura.update_layout(
        template="plotly_white",
        height=altura,
        margin={"l": 18, "r": 18, "t": 28, "b": 24},
        font={"family": "Inter, Arial, sans-serif", "color": "#253746", "size": 12},
        paper_bgcolor="white",
        plot_bgcolor="white",
        colorway=CORES,
        hoverlabel={"bgcolor": "#173b57", "font_color": "white"},
    )
    figura.update_xaxes(showgrid=True, gridcolor="#edf1f4", zeroline=False)
    figura.update_yaxes(showgrid=False, zeroline=False)
    return figura


def _grafico_mensal(df, meses):
    # O período inclui ano e mês para que anos diferentes não sejam combinados.
    dados = df.assign(periodo_mes=df["data"].dt.strftime("%Y-%m"))
    agrupado = (
        dados.groupby("periodo_mes")
        .agg(acidentes=("id", "count"), mortos=("mortos", "sum"))
        .reindex(meses, fill_value=0)
    )
    rotulos = [_rotulo_mes(mes) for mes in meses]
    figura = go.Figure()
    figura.add_trace(
        go.Scatter(
            x=rotulos,
            y=agrupado["acidentes"],
            name="Acidentes",
            mode="lines+markers",
            line={"color": CORES[0], "width": 3},
            marker={"size": 7},
        )
    )
    figura.add_trace(
        go.Scatter(
            x=rotulos,
            y=agrupado["mortos"],
            name="Mortos",
            mode="lines+markers",
            yaxis="y2",
            line={"color": CORES[3], "width": 3},
            marker={"size": 7},
        )
    )
    figura.update_layout(
        title="Acidentes e mortos por mês",
        xaxis_title="Mês",
        yaxis={"title": "Acidentes", "rangemode": "tozero"},
        yaxis2={
            "title": "Mortos",
            "overlaying": "y",
            "side": "right",
            "rangemode": "tozero",
            "showgrid": False,
        },
        legend={"orientation": "h", "y": 1.12, "x": 1, "xanchor": "right"},
    )
    return _configurar_figura(figura, altura=390)


def _grafico_barras(series, titulo, titulo_x):
    ordenada = series.sort_values(ascending=True)
    figura = go.Figure(
        go.Bar(
            x=ordenada.values,
            y=ordenada.index.astype(str),
            orientation="h",
            marker_color=CORES[0],
            hovertemplate="%{y}<br>Acidentes: %{x:,}<extra></extra>",
        )
    )
    figura.update_layout(title=titulo, xaxis_title=titulo_x, yaxis_title="")
    return _configurar_figura(figura, altura=max(350, min(620, 48 * len(ordenada) + 100)))


def _grafico_rosca(df, coluna, titulo):
    contagens = (
        df[coluna]
        .fillna("Não informado")
        .astype(str)
        .value_counts()
        .sort_values(ascending=False)
    )
    figura = go.Figure(
        go.Pie(
            labels=contagens.index,
            values=contagens.values,
            hole=0.62,
            sort=False,
            marker={"colors": CORES},
            textinfo="percent",
            hovertemplate="%{label}<br>Acidentes: %{value:,}<br>%{percent}<extra></extra>",
        )
    )
    figura.update_layout(title=titulo, showlegend=True, legend={"orientation": "h", "y": -0.12})
    return _configurar_figura(figura, altura=355)


def _preparar_tabelas(df):
    # A camada de dados já fornece o rótulo BR + faixa de 10 km.
    trechos = df.loc[df["trecho"] != "NÃO INFORMADO"]
    if not trechos.empty:
        resumo_trechos = (
            trechos.groupby("trecho", as_index=False)
            .agg(
                acidentes=("id", "count"),
                mortos=("mortos", "sum"),
                feridos_graves=("feridos_graves", "sum"),
            )
            .sort_values(
                ["acidentes", "mortos", "trecho"],
                ascending=[False, False, True],
            )
            .head(10)
        )
        tabela_trechos = [
            {
                "trecho": linha.trecho,
                "acidentes": _formatar_inteiro(linha.acidentes),
                "mortos": _formatar_inteiro(linha.mortos),
                "feridos_graves": _formatar_inteiro(linha.feridos_graves),
            }
            for linha in resumo_trechos.itertuples(index=False)
        ]
    else:
        tabela_trechos = []

    resumo_municipios = (
        df.groupby(["municipio", "uf"], dropna=False, as_index=False)
        .agg(
            acidentes=("id", "count"),
            mortos=("mortos", "sum"),
            feridos_graves=("feridos_graves", "sum"),
        )
        .sort_values(
            ["acidentes", "mortos", "municipio", "uf"],
            ascending=[False, False, True, True],
            na_position="last",
        )
        .head(10)
    )
    tabela_municipios = [
        {
            "municipio": (
                f"{'Não informado' if pd.isna(linha.municipio) else linha.municipio} / "
                f"{'UF não informada' if pd.isna(linha.uf) else linha.uf}"
            ),
            "acidentes": _formatar_inteiro(linha.acidentes),
            "mortos": _formatar_inteiro(linha.mortos),
            "feridos_graves": _formatar_inteiro(linha.feridos_graves),
        }
        for linha in resumo_municipios.itertuples(index=False)
    ]
    return tabela_trechos, tabela_municipios


def dashboard(request):
    df = carregar_dados()
    periodo_mes = df["data"].dt.strftime("%Y-%m")
    meses = sorted(periodo_mes.dropna().unique().tolist())
    if not meses:
        raise ValueError("O arquivo não contém datas válidas para montar o painel.")

    ufs = sorted(df["uf"].dropna().astype(str).unique().tolist())
    uf = request.GET.get("uf", "")
    resposta = _validar_opcao(uf, ufs, "UF")
    if resposta:
        return resposta

    df_uf = df if not uf else df.loc[df["uf"].astype(str) == uf]
    brs = [
        str(valor)
        for valor in sorted({int(valor) for valor in df_uf["br"].dropna().unique()})
    ]
    municipios = sorted(df_uf["municipio"].dropna().astype(str).unique().tolist())
    causas = sorted(df["causa_acidente"].dropna().astype(str).unique().tolist())
    tipos = sorted(df["tipo_acidente"].dropna().astype(str).unique().tolist())
    classificacoes = sorted(
        df["classificacao_acidente"].dropna().astype(str).unique().tolist()
    )
    fases = sorted(df["fase_dia"].dropna().astype(str).unique().tolist())
    condicoes = sorted(
        df["condicao_metereologica"].dropna().astype(str).unique().tolist()
    )

    filtros = {
        "uf": uf,
        "br": request.GET.get("br", ""),
        "municipio": request.GET.get("municipio", ""),
        "mes_inicio": request.GET.get("mes_inicio", meses[0]),
        "mes_fim": request.GET.get("mes_fim", meses[-1]),
        "causa_acidente": request.GET.get("causa_acidente", ""),
        "tipo_acidente": request.GET.get("tipo_acidente", ""),
        "classificacao_acidente": request.GET.get("classificacao_acidente", ""),
        "fase_dia": request.GET.get("fase_dia", ""),
        "condicao_metereologica": request.GET.get("condicao_metereologica", ""),
    }

    opcoes = [
        (filtros["br"], brs, "BR"),
        (filtros["municipio"], municipios, "município"),
        (filtros["mes_inicio"], meses, "mês inicial"),
        (filtros["mes_fim"], meses, "mês final"),
        (filtros["causa_acidente"], causas, "causa"),
        (filtros["tipo_acidente"], tipos, "tipo de acidente"),
        (filtros["classificacao_acidente"], classificacoes, "classificação"),
        (filtros["fase_dia"], fases, "fase do dia"),
        (filtros["condicao_metereologica"], condicoes, "condição meteorológica"),
    ]
    for valor, disponiveis, nome in opcoes:
        resposta = _validar_opcao(valor, disponiveis, nome)
        if resposta:
            return resposta

    if filtros["mes_inicio"] > filtros["mes_fim"]:
        return HttpResponseBadRequest("O mês inicial deve ser anterior ou igual ao mês final.")

    mascara = periodo_mes.between(filtros["mes_inicio"], filtros["mes_fim"])
    for coluna, filtro in (
        ("uf", filtros["uf"]),
        ("municipio", filtros["municipio"]),
        ("causa_acidente", filtros["causa_acidente"]),
        ("tipo_acidente", filtros["tipo_acidente"]),
        ("classificacao_acidente", filtros["classificacao_acidente"]),
        ("fase_dia", filtros["fase_dia"]),
        ("condicao_metereologica", filtros["condicao_metereologica"]),
    ):
        if filtro:
            mascara &= df[coluna].astype("string") == filtro
    if filtros["br"]:
        mascara &= df["br"] == int(filtros["br"])
    filtrado = df.loc[mascara].copy()

    # Os cartões usam a definição centralizada dos indicadores da camada de dados.
    kpis = []
    for chave in (
        "acidentes",
        "mortos",
        "feridos_graves",
        "feridos_leves",
        "veiculos",
        "gravidade",
    ):
        indicador = INDICADORES[chave]
        valor = calcular_kpi(filtrado, chave)
        if indicador["tipo"] == "razao":
            valor_formatado = f"{valor:.2f}".replace(".", ",")
            unidade = "mortos por 100 acidentes"
        else:
            valor_formatado = _formatar_inteiro(valor)
            unidade = ""
        kpis.append(
            {
                "rotulo": indicador["nome"],
                "valor": valor_formatado,
                "unidade": unidade,
            }
        )
    acidentes = calcular_kpi(filtrado, "acidentes")

    meses_no_periodo = [
        mes for mes in meses if filtros["mes_inicio"] <= mes <= filtros["mes_fim"]
    ]
    series_causas = (
        filtrado["causa_acidente"].dropna().value_counts().head(10).sort_values()
    )
    series_tipos = filtrado["tipo_acidente"].dropna().value_counts().sort_values()

    if filtros["uf"]:
        serie_ranking = (
            filtrado["br"].dropna().astype(int).astype(str).value_counts().sort_values()
        )
        serie_ranking.index = [f"BR-{valor}" for valor in serie_ranking.index]
        titulo_ranking = f"Ranking de acidentes por BR · {filtros['uf']}"
        eixo_ranking = "Acidentes"
    else:
        serie_ranking = filtrado["uf"].dropna().value_counts().sort_values()
        titulo_ranking = "Ranking de acidentes por UF"
        eixo_ranking = "Acidentes"

    contagem_horas = (
        filtrado.groupby(["dia_semana", "hora"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=DIAS_SEMANA, columns=range(24), fill_value=0)
    )
    heatmap = go.Figure(
        go.Heatmap(
            z=contagem_horas.values,
            x=[f"{hora:02d}:00" for hora in range(24)],
            y=DIAS_SEMANA,
            colorscale="YlOrRd",
            colorbar={"title": "Acidentes"},
            hovertemplate="%{y}<br>%{x}<br>Acidentes: %{z}<extra></extra>",
        )
    )
    heatmap.update_layout(
        title="Acidentes por dia da semana e hora",
        xaxis_title="Hora do dia",
        yaxis_title="Dia da semana",
    )
    heatmap = _configurar_figura(heatmap, altura=390)

    dados_mapa = filtrado.dropna(subset=["latitude", "longitude"])
    mapa = px.scatter_map(
        dados_mapa,
        lat="latitude",
        lon="longitude",
        color="mortos",
        color_continuous_scale="YlOrRd",
        hover_name="municipio",
        hover_data={
            "uf": True,
            "br": True,
            "km": ":.1f",
            "tipo_acidente": True,
            "mortos": True,
            "latitude": False,
            "longitude": False,
        },
        center={"lat": -14.2, "lon": -51.9},
        zoom=3,
        map_style="open-street-map",
        opacity=0.65,
        height=540,
        title="Localização dos acidentes",
    )
    mapa.update_traces(marker={"size": 7})
    mapa.update_layout(margin={"l": 0, "r": 0, "t": 45, "b": 0})

    figuras = [
        ("grafico-mensal", _grafico_mensal(filtrado, meses_no_periodo)),
        (
            "grafico-causas",
            _grafico_barras(series_causas, "10 principais causas", "Acidentes"),
        ),
        (
            "grafico-tipos",
            _grafico_barras(series_tipos, "Acidentes por tipo", "Acidentes"),
        ),
        (
            "grafico-ranking",
            _grafico_barras(serie_ranking, titulo_ranking, eixo_ranking),
        ),
        ("grafico-calor", heatmap),
        (
            "grafico-fase",
            _grafico_rosca(filtrado, "fase_dia", "Acidentes por fase do dia"),
        ),
        (
            "grafico-condicao",
            _grafico_rosca(
                filtrado,
                "condicao_metereologica",
                "Acidentes por condição meteorológica",
            ),
        ),
        ("grafico-mapa", mapa),
    ]
    graficos = [
        {"id": identificador, "figura": json.loads(figura.to_json())}
        for identificador, figura in figuras
    ]
    tabela_trechos, tabela_municipios = _preparar_tabelas(filtrado)

    return render(
        request,
        "painel/dashboard.html",
        {
            "kpis": kpis,
            "graficos": graficos,
            "filtros": filtros,
            "ufs": ufs,
            "brs": brs,
            "municipios": municipios,
            "meses": [{"valor": mes, "rotulo": _rotulo_mes(mes)} for mes in meses],
            "causas": causas,
            "tipos": tipos,
            "classificacoes": classificacoes,
            "fases": fases,
            "condicoes": condicoes,
            "tabela_trechos": tabela_trechos,
            "tabela_municipios": tabela_municipios,
            "total_filtrado": _formatar_inteiro(acidentes),
        },
    )
