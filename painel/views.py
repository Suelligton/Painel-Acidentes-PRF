import textwrap
from io import StringIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from django.http import Http404, HttpResponse
from django.shortcuts import render
from plotly.offline import get_plotlyjs, plot
from plotly.subplots import make_subplots

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

CONFIG_GRAFICO_HOME = {"displayModeBar": False, "displaylogo": False}
PESOS_UPS = {
    "Sem Vítimas": 1,
    "Com Vítimas Feridas": 5,
    "Com Vítimas Fatais": 13,
}
UFS_NORDESTE = {"MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA"}

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


def _formatar_kpi(chave, valor):
    if INDICADORES[chave]["tipo"] == "razao":
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return _formatar_inteiro(valor)


def _formatar_percentual_risco(valor):
    return f"{valor:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def _letalidade(df):
    if df.empty:
        return None
    return float(df["mortos"].sum()) / len(df) * 100


def _letalidade_formatada(df):
    valor = _letalidade(df)
    return "—" if valor is None else _formatar_percentual_risco(valor)


def _rotulo_br(valor):
    if pd.isna(valor) or int(valor) == 0:
        return "Não informada"
    return f"BR-{int(valor)}"


def _rotulo_trecho(valor):
    texto = str(valor)
    if texto.startswith("BR-0 "):
        return texto.replace("BR-0", "Não informada", 1)
    return texto


def _rotulo_periodo(periodo):
    ano, numero_mes = periodo.split("-")
    return f"{MESES_NOME[int(numero_mes)]}/{ano}"


def _periodos_filtrados(df, filtros):
    return [
        periodo
        for periodo in _periodos(df)
        if (not filtros["mes_ini"] or periodo >= filtros["mes_ini"])
        and (not filtros["mes_fim"] or periodo <= filtros["mes_fim"])
    ]


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


def _figura_div(figura, config=None):
    return plot(
        figura,
        output_type="div",
        include_plotlyjs=False,
        config=config if config is not None else {"displaylogo": False},
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


def _quebrar_rotulo_barras(rotulo):
    linhas = textwrap.wrap(
        str(rotulo),
        width=28,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return "<br>".join(linhas) or " "


def _altura_barras(rotulos, altura_minima=300):
    total_linhas = sum(rotulo.count("<br>") + 1 for rotulo in rotulos)
    return max(altura_minima, total_linhas * 28 + 40)


def _figura_barras(contagens, titulo, cor, altura_minima=300):
    contagens = contagens.sort_values(ascending=True)
    categorias = [str(categoria) for categoria in contagens.index]
    rotulos = [_quebrar_rotulo_barras(categoria) for categoria in categorias]
    tabela = pd.DataFrame(
        {
            "categoria": rotulos,
            "categoria_completa": categorias,
            "acidentes": contagens.to_numpy(),
        }
    )
    figura = px.bar(
        tabela,
        x="acidentes",
        y="categoria",
        orientation="h",
        text="acidentes",
        custom_data=["categoria_completa"],
        title=titulo,
        color_discrete_sequence=[cor or CORES_PMPB["vermelho"]],
        template="plotly_white",
    )
    figura.update_traces(
        texttemplate="%{x:,.0f}",
        textposition="inside",
        textfont_color="white",
        cliponaxis=False,
        hovertemplate="%{customdata[0]}<br>Acidentes: %{x:,.0f}<extra></extra>",
    )
    figura = _aplicar_tema(figura)
    figura.update_layout(
        xaxis_title="Acidentes",
        yaxis_title="",
        height=_altura_barras(rotulos, altura_minima),
        margin={"l": 160, "r": 25, "t": 55 if titulo else 10, "b": 30},
    )
    figura.update_yaxes(automargin=True)
    return figura


def _grafico_barras(df, coluna, titulo, limite=None, cor=None):
    contagens = df[coluna].value_counts()
    if limite is not None:
        contagens = contagens.head(limite)
    return _figura_barras(
        contagens,
        titulo,
        cor or CORES_PMPB["vermelho"],
    )


def _serie_indicador(df, colunas_grupo, chave):
    colunas = [colunas_grupo] if isinstance(colunas_grupo, str) else colunas_grupo
    agrupamento = df.groupby(colunas, dropna=False, sort=False)
    indicador = INDICADORES[chave]

    if indicador["tipo"] == "contagem":
        return agrupamento.size()
    if indicador["tipo"] == "soma":
        return agrupamento[indicador["coluna"]].sum()
    if indicador["tipo"] == "razao":
        return agrupamento[indicador["coluna"]].sum().div(agrupamento.size()).mul(100)
    raise ValueError(f"Tipo de indicador não suportado: {indicador['tipo']}")


CORES_CARTOES_HOME = {
    "acidentes": CORES_PMPB["cinza"],
    "mortos": CORES_PMPB["vermelho"],
    "feridos_graves": CORES_PMPB["vermelho_escuro"],
    "feridos_leves": CORES_PMPB["dourado"],
    "veiculos": CORES_PMPB["preto"],
    "gravidade": CORES_PMPB["vermelho_escuro"],
}


def _serie_mensal_home(df, periodos, chave):
    if df.empty or not periodos:
        return pd.Series(dtype="float64")
    dados = df.assign(periodo=df["data"].dt.strftime("%Y-%m"))
    return _serie_indicador(dados, "periodo", chave).reindex(periodos, fill_value=0)


def _grafico_sparkline(periodos, valores, cor):
    if valores.empty:
        return None

    figura = go.Figure(
        go.Scatter(
            x=periodos,
            y=valores.to_numpy(),
            mode="lines+markers",
            line={"color": cor, "width": 2},
            marker={"color": cor, "size": 3},
            hoverinfo="skip",
        )
    )
    figura.update_layout(
        template="plotly_white",
        height=40,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    figura.update_xaxes(visible=False, fixedrange=True)
    figura.update_yaxes(visible=False, fixedrange=True, rangemode="tozero")
    return _figura_div(figura, config=CONFIG_GRAFICO_HOME)


def _formatar_variacao_home(valor):
    return f"{valor:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def _preparar_cartoes_home(df, periodos):
    cartoes = _preparar_kpis(df, incluir_chave=True)
    for cartao in cartoes:
        chave = cartao["chave"]
        valores = _serie_mensal_home(df, periodos, chave)
        anterior = valores.iloc[-2] if len(valores) > 1 else None
        atual = valores.iloc[-1] if len(valores) > 1 else None
        tipo_variacao = "neutra"
        variacao = "Sem comparação"

        if anterior is not None and atual is not None:
            if anterior == 0:
                if atual > 0:
                    variacao = "Novo"
                    tipo_variacao = "piorou"
                else:
                    variacao = "0,0%"
            else:
                percentual = (atual - anterior) / abs(anterior) * 100
                variacao = _formatar_variacao_home(percentual)
                if percentual > 0:
                    tipo_variacao = "piorou"
                elif percentual < 0:
                    tipo_variacao = "melhorou"

        cor = CORES_CARTOES_HOME[chave]
        cartao.update(
            {
                "cor": cor,
                "variacao": variacao,
                "tipo_variacao": tipo_variacao,
                "sparkline": _grafico_sparkline(periodos, valores, cor),
            }
        )
    return cartoes


def _grafico_evolucao_home(df, periodos):
    if df.empty or not periodos:
        return None

    mensal = (
        df.assign(periodo=df["data"].dt.strftime("%Y-%m"))
        .groupby("periodo")
        .agg(acidentes=("id", "size"), mortos=("mortos", "sum"))
        .reindex(periodos, fill_value=0)
    )
    rotulos = [_rotulo_periodo(periodo) for periodo in periodos]
    figura = make_subplots(specs=[[{"secondary_y": True}]])
    figura.add_trace(
        go.Bar(
            x=rotulos,
            y=mensal["acidentes"],
            name="Acidentes",
            marker_color=CORES_PMPB["cinza"],
            hovertemplate="%{x}<br>Acidentes: %{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )
    figura.add_trace(
        go.Scatter(
            x=rotulos,
            y=mensal["mortos"],
            name="Mortos",
            mode="lines+markers",
            line={"color": CORES_PMPB["vermelho"], "width": 2.5},
            marker={"size": 6},
            hovertemplate="%{x}<br>Mortos: %{y:,.0f}<extra></extra>",
        ),
        secondary_y=True,
    )
    figura.update_layout(
        template="plotly_white",
        height=340,
        margin={"l": 10, "r": 10, "t": 10, "b": 38},
        separators=",.",
        barmode="group",
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.18,
            "xanchor": "center",
            "x": 0.5,
        },
        hovermode="x unified",
    )
    figura.update_xaxes(tickangle=-20, title_text="")
    figura.update_yaxes(title_text="", rangemode="tozero", secondary_y=False)
    figura.update_yaxes(title_text="", rangemode="tozero", secondary_y=True)
    return figura


def _grafico_causas_home(df):
    contagens = df["causa_acidente"].value_counts().head(5).sort_values()
    figura = _figura_barras(contagens, None, CORES_PMPB["vermelho"])
    figura.update_layout(title=None, margin={"l": 160, "r": 10, "t": 10, "b": 10})
    figura.update_yaxes(automargin=True)
    return figura


def _grafico_classificacao_home(df):
    contagens = _agrupar_fatias_pequenas(
        df["classificacao_acidente"].value_counts()
    )
    tabela = contagens.rename_axis("classificacao").reset_index(name="acidentes")
    figura = px.pie(
        tabela,
        names="classificacao",
        values="acidentes",
        hole=0.62,
        color="classificacao",
        color_discrete_map={
            **CORES_CLASSIFICACAO,
            "Outros": CORES_PMPB["preto"],
        },
        category_orders={
            "classificacao": [
                "Com Vítimas Fatais",
                "Com Vítimas Feridas",
                "Sem Vítimas",
            ]
        },
        template="plotly_white",
    )
    figura.update_traces(
        textinfo="percent",
        textposition="inside",
        hovertemplate="%{label}<br>Acidentes: %{value:,.0f}<extra></extra>",
    )
    figura.update_layout(
        height=300,
        margin={"l": 10, "r": 10, "t": 10, "b": 36},
        separators=",.",
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.08,
            "xanchor": "center",
            "x": 0.5,
        },
    )
    figura.add_annotation(
        text=f"<b>{_formatar_inteiro(len(df))}</b><br>acidentes",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 14, "color": CORES_PMPB["preto"]},
    )
    return _aplicar_tema(figura)


def _grafico_ranking_home(df, filtros):
    if filtros["uf"]:
        contagens = df["br"].dropna().astype(int).value_counts()
        contagens.index = [_rotulo_br(valor) for valor in contagens.index]
        cor = CORES_PMPB["vermelho_escuro"]
    else:
        contagens = df["uf"].value_counts()
        cor = CORES_PMPB["vermelho"]
    contagens = contagens.head(5).sort_values()
    figura = _figura_barras(contagens, None, cor)
    figura.update_layout(title=None, margin={"l": 160, "r": 10, "t": 10, "b": 10})
    figura.update_yaxes(automargin=True)
    return figura


def _grafico_mapa_home(df, filtros):
    pontos = df.dropna(subset=["latitude", "longitude"]).copy()
    pontos = pontos.loc[
        pontos["latitude"].between(-90, 90)
        & pontos["longitude"].between(-180, 180)
    ]
    if pontos.empty:
        return None

    centro = {
        "lat": float(pontos["latitude"].mean()),
        "lon": float(pontos["longitude"].mean()),
    }
    if len(pontos) > 3000:
        pontos = pontos.sample(n=3000, random_state=1)

    pontos["localidade_hover"] = (
        pontos["municipio"].astype("string") + " - " + pontos["uf"].astype("string")
    )
    pontos["trecho_hover"] = pontos.apply(
        lambda linha: (
            f"BR-{int(linha['br'])}, km {linha['km']:.1f}".replace(".", ",")
            if pd.notna(linha["br"]) and pd.notna(linha["km"])
            else "Trecho não informado"
        ),
        axis=1,
    )
    datas = pontos["data_inversa"].dt.strftime("%d/%m/%Y").fillna("Data não informada")
    horarios = pontos["horario"].astype("string").fillna("Horário não informado")
    pontos["data_hora_hover"] = datas + " " + horarios

    zoom = 9 if filtros["municipio"] else 6 if filtros["uf"] else 3.3
    figura = px.scatter_map(
        pontos,
        lat="latitude",
        lon="longitude",
        color="classificacao_acidente",
        color_discrete_map=CORES_CLASSIFICACAO,
        category_orders={
            "classificacao_acidente": [
                "Com Vítimas Fatais",
                "Com Vítimas Feridas",
                "Sem Vítimas",
            ]
        },
        hover_name="localidade_hover",
        custom_data=[
            "trecho_hover",
            "data_hora_hover",
            "causa_acidente",
            "tipo_acidente",
            "classificacao_acidente",
            "mortos",
            "feridos",
        ],
        map_style="carto-positron",
        center=centro,
        zoom=zoom,
        opacity=0.7,
        height=340,
        template="plotly_white",
    )
    figura.update_traces(
        marker={"size": 7},
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "%{customdata[0]}<br>"
            "Data e hora: %{customdata[1]}<br>"
            "Causa: %{customdata[2]}<br>"
            "Tipo: %{customdata[3]}<br>"
            "Classificação: %{customdata[4]}<br>"
            "Mortos: %{customdata[5]} | Feridos: %{customdata[6]}"
            "<extra></extra>"
        ),
    )
    figura.update_layout(
        height=340,
        showlegend=False,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
    )
    return _aplicar_tema(figura)


def _rotulo_grupo(valor):
    if isinstance(valor, tuple):
        partes = ["NÃO INFORMADO" if pd.isna(parte) else str(parte) for parte in valor]
        return " / ".join(partes)
    return "NÃO INFORMADO" if pd.isna(valor) else str(valor)


def _grafico_barras_indicador(df, coluna, chave, titulo, limite=10):
    valores = _serie_indicador(df, coluna, chave).sort_values(ascending=False).head(limite)
    valores = valores.sort_values(ascending=True)
    categorias = [
        _rotulo_br(valor) if coluna == "br" else _rotulo_grupo(valor)
        for valor in valores.index
    ]
    rotulos = [_quebrar_rotulo_barras(categoria) for categoria in categorias]
    tabela = pd.DataFrame(
        {
            "categoria": rotulos,
            "categoria_completa": categorias,
            "valor": valores.to_numpy(),
        }
    )
    casas_decimais = 2 if INDICADORES[chave]["tipo"] == "razao" else 0
    figura = px.bar(
        tabela,
        x="valor",
        y="categoria",
        orientation="h",
        text="valor",
        custom_data=["categoria_completa"],
        title=titulo,
        color_discrete_sequence=[CORES_PMPB["vermelho"]],
        template="plotly_white",
    )
    figura.update_traces(
        texttemplate=f"%{{x:,.{casas_decimais}f}}",
        textposition="inside",
        textfont_color="white",
        cliponaxis=False,
        hovertemplate=(
            "%{customdata[0]}<br>"
            + INDICADORES[chave]["nome"]
            + f": %{{x:,.{casas_decimais}f}}<extra></extra>"
        ),
    )
    figura = _aplicar_tema(figura)
    figura.update_layout(
        xaxis_title=INDICADORES[chave]["nome"],
        yaxis_title="",
        height=_altura_barras(rotulos),
        margin={"l": 160, "r": 30, "t": 55, "b": 35},
    )
    figura.update_yaxes(automargin=True)
    return figura


def _grafico_mensal_indicador(df, periodos, chave):
    dados = df.assign(periodo=df["data"].dt.strftime("%Y-%m"))
    valores = _serie_indicador(dados, "periodo", chave).reindex(periodos, fill_value=0)
    tabela = valores.rename("valor").reset_index()
    tabela["mes"] = tabela["periodo"].map(_rotulo_periodo)
    rotulos = [_rotulo_periodo(periodo) for periodo in periodos]
    figura = px.line(
        tabela,
        x="mes",
        y="valor",
        markers=True,
        category_orders={"mes": rotulos},
        title=f"Evolução mensal: {INDICADORES[chave]['nome']}",
        color_discrete_sequence=[CORES_PMPB["vermelho"]],
        template="plotly_white",
    )
    figura.update_traces(
        line={"width": 3},
        hovertemplate="%{x}<br>"
        + INDICADORES[chave]["nome"]
        + ": %{y:,.2f}<extra></extra>",
    )
    figura.update_yaxes(title_text=INDICADORES[chave]["nome"], rangemode="tozero")
    figura.update_xaxes(title_text="Mês", tickangle=-25)
    return _aplicar_tema(figura)


def _grafico_calor_indicador(df, chave, filtros=None):
    valores = _serie_indicador(df, ["dia_semana", "hora"], chave)
    tabela = (
        valores.unstack("hora")
        .reindex(index=DIAS_SEMANA, columns=range(24), fill_value=0)
    )
    filtros = filtros or {}
    mostrar_valores = bool(filtros.get("uf") or filtros.get("municipio"))
    texto = (
        (".2f" if INDICADORES[chave]["tipo"] == "razao" else True)
        if mostrar_valores
        else False
    )
    figura = px.imshow(
        tabela,
        x=[f"{hora:02d}" for hora in range(24)],
        y=DIAS_SEMANA,
        aspect="auto",
        text_auto=texto,
        labels={
            "x": "Hora do dia",
            "y": "Dia da semana",
            "color": INDICADORES[chave]["nome"],
        },
        color_continuous_scale=[
            [0, "#F5F5F4"],
            [0.5, CORES_PMPB["dourado"]],
            [1, CORES_PMPB["vermelho"]],
        ],
        title=f"{INDICADORES[chave]['nome']} por dia da semana e hora",
        template="plotly_white",
    )
    return _aplicar_tema(figura)


def _tabelas_indicador(df, chave):
    trechos = _serie_indicador(df, "trecho", chave)
    trechos = trechos[trechos.index != "NÃO INFORMADO"].sort_values(ascending=False).head(10)
    municipios = _serie_indicador(df, ["municipio", "uf"], chave)
    municipios = municipios.sort_values(ascending=False).head(10)

    return (
        [
            {"nome": _rotulo_trecho(_rotulo_grupo(trecho)), "valor": _formatar_kpi(chave, valor)}
            for trecho, valor in trechos.items()
        ],
        [
            {"nome": _rotulo_grupo(municipio), "valor": _formatar_kpi(chave, valor)}
            for municipio, valor in municipios.items()
        ],
    )


def _comparar_trimestres(df, filtros, chave):
    # A comparação usa os trimestres fixos e conserva os filtros não temporais.
    filtros_comparacao = filtros.copy()
    filtros_comparacao["mes_ini"] = ""
    filtros_comparacao["mes_fim"] = ""
    dados = aplicar_filtros(df, filtros_comparacao)
    meses = dados["data"].dt.month
    primeiro_trimestre = dados.loc[meses.between(1, 3)]
    terceiro_trimestre = dados.loc[meses.between(7, 9)]
    valor_primeiro = calcular_kpi(primeiro_trimestre, chave)
    valor_terceiro = calcular_kpi(terceiro_trimestre, chave)

    if valor_primeiro:
        variacao = (valor_terceiro - valor_primeiro) / abs(valor_primeiro) * 100
        variacao_formatada = (
            f"{variacao:+,.2f}%"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    else:
        variacao_formatada = "—"

    return {
        "primeiro": _formatar_kpi(chave, valor_primeiro),
        "terceiro": _formatar_kpi(chave, valor_terceiro),
        "variacao": variacao_formatada,
    }


def _grafico_calor(df, filtros=None):
    tabela = (
        df.groupby(["dia_semana", "hora"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=DIAS_SEMANA, columns=range(24), fill_value=0)
    )
    filtros = filtros or {}
    figura = px.imshow(
        tabela,
        x=[f"{hora:02d}" for hora in range(24)],
        y=DIAS_SEMANA,
        aspect="auto",
        text_auto=bool(filtros.get("uf") or filtros.get("municipio")),
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


def _agrupar_fatias_pequenas(contagens):
    total = contagens.sum()
    if not total:
        return contagens

    pequenas = contagens.loc[contagens / total < 0.03]
    if pequenas.empty:
        return contagens

    agrupadas = contagens.drop(index=pequenas.index).copy()
    outras = pequenas.sum()
    if "Outros" in agrupadas.index:
        agrupadas.loc["Outros"] += outras
    else:
        agrupadas.loc["Outros"] = outras
    return agrupadas.sort_values(ascending=False)


def _grafico_rosca(df, coluna, titulo):
    contagens = _agrupar_fatias_pequenas(df[coluna].value_counts())
    tabela = contagens.rename_axis("categoria").reset_index(name="acidentes")
    figura = px.pie(
        tabela,
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


def _adicionar_ups(df):
    dados = df.copy()
    dados["ups"] = (
        dados["classificacao_acidente"]
        .map(PESOS_UPS)
        .fillna(1)
        .astype("int64")
    )
    return dados


def _resumo_risco_por_grupo(df, coluna):
    resumo = (
        df.groupby(coluna, dropna=False)
        .agg(
            acidentes=("id", "size"),
            mortos=("mortos", "sum"),
            feridos_graves=("feridos_graves", "sum"),
        )
    )
    if not resumo.empty:
        resumo["letalidade"] = resumo["mortos"].div(resumo["acidentes"]) * 100
    return resumo


def _grafico_risco_causas(df, filtros):
    resumo = _resumo_risco_por_grupo(df, "causa_acidente")
    minimo = (
        100
        if not (filtros.get("uf") or filtros.get("br") or filtros.get("municipio"))
        else 30
    )
    resumo = resumo.loc[resumo["acidentes"] >= minimo].copy()
    if resumo.empty:
        return None

    top_causas = resumo.nlargest(5, "mortos").index
    tabela = resumo.rename_axis("causa").reset_index()
    rotulos_por_causa = {
        causa: _quebrar_rotulo_barras(causa) for causa in top_causas
    }
    posicoes = [
        "top center",
        "bottom center",
        "middle right",
        "middle left",
        "top right",
    ]
    posicoes_por_causa = dict(zip(top_causas, posicoes))
    tabela["rotulo"] = tabela["causa"].map(rotulos_por_causa).fillna("")
    tabela["posicao_rotulo"] = (
        tabela["causa"].map(posicoes_por_causa).fillna("top center")
    )
    figura = px.scatter(
        tabela,
        x="acidentes",
        y="letalidade",
        size="mortos",
        size_max=42,
        text="rotulo",
        custom_data=["causa", "mortos"],
        color_discrete_sequence=[CORES_PMPB["vermelho"]],
        template="plotly_white",
    )
    figura.update_traces(
        marker={"opacity": 0.72, "line": {"color": "white", "width": 1}},
        textposition=tabela["posicao_rotulo"].tolist(),
        textfont={"size": 10, "color": CORES_PMPB["preto"]},
        cliponaxis=False,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Acidentes: %{x:,.0f}<br>"
            "Letalidade: %{y:.2f}%<br>"
            "Mortos: %{customdata[1]:,.0f}<extra></extra>"
        ),
    )
    mediana_x = float(resumo["acidentes"].median())
    mediana_y = float(resumo["letalidade"].median())
    figura.add_shape(
        type="rect",
        x0=mediana_x,
        x1=float(resumo["acidentes"].max()),
        y0=mediana_y,
        y1=float(resumo["letalidade"].max()),
        fillcolor="rgba(200, 16, 46, 0.10)",
        line={"width": 0},
        layer="below",
    )
    figura.add_vline(
        x=mediana_x,
        line_dash="dash",
        line_color=CORES_PMPB["cinza"],
    )
    figura.add_hline(
        y=mediana_y,
        line_dash="dash",
        line_color=CORES_PMPB["cinza"],
    )
    figura.add_annotation(
        x=0.98,
        y=0.97,
        xref="paper",
        yref="paper",
        text="<b>Prioridade</b>",
        showarrow=False,
        xanchor="right",
        font={"color": CORES_PMPB["vermelho_escuro"], "size": 12},
    )
    figura.update_layout(
        xaxis_title="Número de acidentes",
        yaxis_title="Letalidade (%)",
        height=420,
        margin={"l": 60, "r": 20, "t": 20, "b": 50},
        showlegend=False,
    )
    figura.update_yaxes(rangemode="tozero")
    return _aplicar_tema(figura)


def _grafico_risco_barras(df, coluna, minimo=30):
    resumo = _resumo_risco_por_grupo(df, coluna)
    resumo = resumo.loc[resumo["acidentes"] >= minimo].copy()
    if resumo.empty:
        return None

    resumo = resumo.sort_values("letalidade", ascending=True)
    tabela = resumo.rename_axis("categoria").reset_index()
    tabela["rotulo"] = tabela["categoria"].map(_quebrar_rotulo_barras)
    figura = px.bar(
        tabela,
        x="letalidade",
        y="rotulo",
        orientation="h",
        text="letalidade",
        custom_data=["categoria", "acidentes"],
        color_discrete_sequence=[CORES_PMPB["vermelho"]],
        template="plotly_white",
    )
    figura.update_traces(
        texttemplate="%{x:.2f}%",
        textposition="inside",
        textfont_color="white",
        cliponaxis=False,
        hovertemplate=(
            "%{customdata[0]}<br>"
            "Letalidade: %{x:.2f}%<br>"
            "Acidentes: %{customdata[1]:,.0f}<extra></extra>"
        ),
    )
    figura = _aplicar_tema(figura)
    rotulos = tabela["rotulo"].tolist()
    figura.update_layout(
        xaxis_title="Letalidade (%)",
        yaxis_title="",
        height=_altura_barras(rotulos),
        margin={"l": 160, "r": 20, "t": 20, "b": 40},
        showlegend=False,
    )
    figura.update_yaxes(automargin=True)
    return figura


def _grafico_risco_horas(df):
    por_hora = (
        df.groupby("hora")
        .agg(acidentes=("id", "size"), mortos=("mortos", "sum"))
        .reindex(range(24), fill_value=0)
    )
    letalidade = (
        por_hora["mortos"]
        .div(por_hora["acidentes"].where(por_hora["acidentes"] > 0))
        .mul(100)
    )
    figura = make_subplots(specs=[[{"secondary_y": True}]])
    figura.add_trace(
        go.Bar(
            x=list(range(24)),
            y=por_hora["acidentes"],
            name="Acidentes",
            marker_color=CORES_PMPB["cinza"],
            hovertemplate="Hora %{x:02d}:00<br>Acidentes: %{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )
    figura.add_trace(
        go.Scatter(
            x=list(range(24)),
            y=letalidade,
            name="Letalidade",
            mode="lines+markers",
            line={"color": CORES_PMPB["vermelho"], "width": 2.5},
            hovertemplate="Hora %{x:02d}:00<br>Letalidade: %{y:.2f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    figura.update_layout(
        template="plotly_white",
        margin={"l": 45, "r": 45, "t": 20, "b": 45},
        separators=",.",
        legend={"orientation": "h", "y": -0.22, "x": 0.5, "xanchor": "center"},
        hovermode="x unified",
    )
    figura.update_xaxes(
        title_text="Hora do dia",
        tickmode="array",
        tickvals=list(range(24)),
        ticktext=[f"{hora:02d}" for hora in range(24)],
    )
    figura.update_yaxes(title_text="Acidentes", rangemode="tozero", secondary_y=False)
    figura.update_yaxes(title_text="Letalidade (%)", rangemode="tozero", secondary_y=True)
    return _aplicar_tema(figura)


def _grafico_mapa_risco(df, filtros):
    pontos = df.loc[
        df["classificacao_acidente"].isin(
            ("Com Vítimas Fatais", "Com Vítimas Feridas")
        )
    ].copy()
    for coluna in ("latitude", "longitude", "ups"):
        pontos[coluna] = pd.to_numeric(pontos[coluna], errors="coerce")
    pontos = pontos.dropna(subset=["latitude", "longitude"])
    pontos = pontos.loc[
        pontos["latitude"].between(-90, 90)
        & pontos["longitude"].between(-180, 180)
    ]
    if pontos.empty:
        return None

    centro = {
        "lat": float(pontos["latitude"].mean()),
        "lon": float(pontos["longitude"].mean()),
    }
    zoom = 9 if filtros.get("municipio") else 6 if filtros.get("uf") else 3.3
    figura = px.density_map(
        pontos,
        lat="latitude",
        lon="longitude",
        z="ups",
        radius=12,
        center=centro,
        zoom=zoom,
        map_style="carto-positron",
        opacity=0.8,
        color_continuous_scale=[
            [0, "rgba(255,255,255,0)"],
            [0.3, "#C9A227"],
            [0.7, "#C8102E"],
            [1, "#7A0C14"],
        ],
        hover_name="municipio",
        hover_data={
            "uf": True,
            "trecho": True,
            "ups": True,
            "latitude": False,
            "longitude": False,
        },
        labels={"ups": "UPS", "uf": "UF", "trecho": "Trecho"},
        template="plotly_white",
    )
    figura = _aplicar_tema(figura)
    figura.update_layout(
        height=520,
        autosize=True,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        map={"center": centro, "zoom": zoom},
        coloraxis_colorbar={
            "title": "Severidade (UPS)",
            "thickness": 12,
            "len": 0.6,
        },
    )
    return figura


def _preparar_cartoes_risco(df, df_completo, filtros):
    noite = df.loc[df["hora"].isin([18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5])]
    dia = df.loc[df["hora"].between(6, 17).fillna(False)]
    fim_semana = df.loc[df["dia_semana"].isin(["sábado", "domingo"])]
    dias_uteis = df.loc[
        df["dia_semana"].isin(
            [
                "segunda-feira",
                "terça-feira",
                "quarta-feira",
                "quinta-feira",
                "sexta-feira",
            ]
        )
    ]

    filtros_benchmark = filtros.copy()
    filtros_benchmark["uf"] = ""
    filtros_benchmark["municipio"] = ""
    base_benchmark = aplicar_filtros(df_completo, filtros_benchmark)
    nordeste = base_benchmark.loc[base_benchmark["uf"].isin(UFS_NORDESTE)]
    uf_selecionada = filtros.get("uf") or "UF não selecionada"

    return [
        {
            "titulo": "Letalidade geral",
            "descricao": "Mortos por 100 acidentes no recorte selecionado.",
            "valor": _letalidade_formatada(df),
        },
        {
            "titulo": "Noite x dia",
            "descricao": "Comparação entre 18h–5h e 6h–17h.",
            "comparacoes": [
                {"rotulo": "Noite", "valor": _letalidade_formatada(noite)},
                {"rotulo": "Dia", "valor": _letalidade_formatada(dia)},
            ],
        },
        {
            "titulo": "Fim de semana x dias úteis",
            "descricao": "Comparação de sábado e domingo com segunda a sexta.",
            "comparacoes": [
                {"rotulo": "Fim de semana", "valor": _letalidade_formatada(fim_semana)},
                {"rotulo": "Dias úteis", "valor": _letalidade_formatada(dias_uteis)},
            ],
        },
        {
            "titulo": "Comparação regional",
            "descricao": "Letalidade da UF selecionada, Nordeste e Brasil.",
            "comparacoes": [
                {
                    "rotulo": uf_selecionada,
                    "valor": (
                        _letalidade_formatada(df)
                        if filtros.get("uf")
                        else "—"
                    ),
                },
                {"rotulo": "Nordeste", "valor": _letalidade_formatada(nordeste)},
                {"rotulo": "Brasil", "valor": _letalidade_formatada(base_benchmark)},
            ],
        },
    ]


def _preparar_tabela_ups(df):
    dados = _adicionar_ups(df)
    dados = dados.loc[dados["trecho"] != "NÃO INFORMADO"]
    trechos = (
        dados.groupby(["trecho", "uf"], dropna=False)
        .agg(
            acidentes=("id", "size"),
            mortos=("mortos", "sum"),
            feridos_graves=("feridos_graves", "sum"),
            ups=("ups", "sum"),
        )
        .sort_values(["ups", "acidentes"], ascending=False)
        .head(15)
        .reset_index()
    )
    maior_ups = trechos["ups"].max() if not trechos.empty else 0
    return [
        {
            "posicao": indice,
            "trecho": _rotulo_trecho(linha.trecho),
            "uf": linha.uf,
            "acidentes": _formatar_inteiro(linha.acidentes),
            "mortos": _formatar_inteiro(linha.mortos),
            "feridos_graves": _formatar_inteiro(linha.feridos_graves),
            "ups": _formatar_inteiro(linha.ups),
            "letalidade": _formatar_percentual_risco(
                linha.mortos / linha.acidentes * 100
            ),
            "largura": linha.ups / maior_ups * 100 if maior_ups else 0,
        }
        for indice, linha in enumerate(trechos.itertuples(index=False), start=1)
    ]


def _grafico_mapa(df, filtros=None):
    pontos = df.dropna(subset=["latitude", "longitude"]).copy()
    pontos = pontos.loc[
        pontos["latitude"].between(-90, 90)
        & pontos["longitude"].between(-180, 180)
    ]
    titulo = "Localização dos acidentes"
    if len(pontos) > 5000:
        pontos = pontos.sample(n=5000, random_state=1)
        titulo += " — amostra de 5.000 pontos"
    if pontos.empty:
        return None

    pontos["localidade_hover"] = (
        pontos["municipio"].astype("string") + " - " + pontos["uf"].astype("string")
    )
    pontos["br_hover"] = pontos["br"].map(
        lambda valor: f"BR-{int(valor)}" if pd.notna(valor) else "BR não informada"
    )
    pontos["km_hover"] = pontos["km"].map(
        lambda valor: f"km {valor:.1f}".replace(".", ",")
        if pd.notna(valor)
        else "km não informado"
    )
    pontos["trecho_hover"] = pontos["br_hover"] + ", " + pontos["km_hover"]
    datas = pontos["data_inversa"].dt.strftime("%d/%m/%Y").fillna("Data não informada")
    horarios = pontos["horario"].astype("string").fillna("Horário não informado")
    pontos["data_hora_hover"] = datas + " " + horarios
    centro = {
        "lat": float(pontos["latitude"].mean()),
        "lon": float(pontos["longitude"].mean()),
    }
    filtros = filtros or {}
    zoom = 9 if filtros.get("municipio") else 6 if filtros.get("uf") else 3.3

    figura = px.scatter_map(
        pontos,
        lat="latitude",
        lon="longitude",
        color="classificacao_acidente",
        color_discrete_map=CORES_CLASSIFICACAO,
        category_orders={
            "classificacao_acidente": [
                "Com Vítimas Fatais",
                "Com Vítimas Feridas",
                "Sem Vítimas",
            ]
        },
        hover_name="localidade_hover",
        custom_data=[
            "trecho_hover",
            "data_hora_hover",
            "causa_acidente",
            "tipo_acidente",
            "classificacao_acidente",
            "mortos",
            "feridos",
        ],
        labels={"classificacao_acidente": "Classificação"},
        map_style="carto-positron",
        center=centro,
        zoom=zoom,
        opacity=0.7,
        title=titulo,
    )
    figura.update_traces(
        marker={"size": 8},
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "%{customdata[0]}<br>"
            "Data e hora: %{customdata[1]}<br>"
            "Causa: %{customdata[2]}<br>"
            "Tipo: %{customdata[3]}<br>"
            "Classificação: %{customdata[4]}<br>"
            "Mortos: %{customdata[5]} | Feridos: %{customdata[6]}"
            "<extra></extra>"
        ),
    )
    figura.update_layout(
        height=600,
        legend_title_text="Classificação",
        margin={"l": 0, "r": 0, "t": 55, "b": 0},
    )
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
                "trecho": _rotulo_trecho(linha.trecho),
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
    mapa = _grafico_mapa(df, filtros)
    if filtros["uf"]:
        contagens_ranking = df["br"].dropna().astype(int).value_counts()
        contagens_ranking.index = [_rotulo_br(valor) for valor in contagens_ranking.index]
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
        "calor": _figura_div(_grafico_calor(df, filtros)),
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


def _preparar_kpis(df, incluir_chave=False):
    kpis = []
    for chave, indicador in INDICADORES.items():
        kpi = {
            "nome": indicador["nome"],
            "descricao": indicador["descricao"],
            "valor": _formatar_kpi(chave, calcular_kpi(df, chave)),
        }
        if incluir_chave:
            kpi["chave"] = chave
        kpis.append(kpi)
    return kpis


def _contexto_comum(request, df, filtros, filtrado, pagina_atual):
    ufs, brs_por_uf, municipios_por_uf = _opcoes_dependentes(df)
    meses = _periodos(df)
    periodo_inicio = (
        _rotulo_periodo(filtros["mes_ini"]) if filtros["mes_ini"] else ""
    )
    periodo_fim = _rotulo_periodo(filtros["mes_fim"]) if filtros["mes_fim"] else ""
    if periodo_inicio and periodo_fim:
        periodo_recorte = (
            periodo_inicio
            if periodo_inicio == periodo_fim
            else f"{periodo_inicio} a {periodo_fim}"
        )
    elif periodo_inicio:
        periodo_recorte = f"A partir de {periodo_inicio}"
    elif periodo_fim:
        periodo_recorte = f"Até {periodo_fim}"
    else:
        periodo_recorte = "Todo o período"

    return {
        "filtros": filtros,
        "recorte": {
            "uf": filtros["uf"] or "Todas",
            "br": f"BR-{filtros['br']}" if filtros["br"] else "Todas",
            "municipio": filtros["municipio"] or "Todos",
            "periodo": periodo_recorte,
        },
        "query_string": request.GET.urlencode(),
        "nav_active": pagina_atual,
        "indicadores_menu": [
            {"chave": chave, "nome": indicador["nome"]}
            for chave, indicador in INDICADORES.items()
        ],
        "ufs": ufs,
        "brs": brs_por_uf[filtros["uf"]],
        "municipios": municipios_por_uf[filtros["uf"]],
        "brs_por_uf": brs_por_uf,
        "municipios_por_uf": municipios_por_uf,
        "meses": [
            {"valor": periodo, "rotulo": _rotulo_periodo(periodo)}
            for periodo in meses
        ],
        "causas": _valores_texto(df, "causa_acidente"),
        "tipos": _valores_texto(df, "tipo_acidente"),
        "classificacoes": _valores_texto(df, "classificacao_acidente"),
        "fases": _valores_texto(df, "fase_dia"),
        "climas": _valores_texto(df, "condicao_metereologica"),
        "total_filtrado": _formatar_inteiro(len(filtrado)),
    }


def home(request):
    df = carregar_dados()
    filtros = ler_filtros(request)
    filtrado = aplicar_filtros(df, filtros)
    periodos = _periodos_filtrados(df, filtros)
    contexto = _contexto_comum(request, df, filtros, filtrado, "home")
    sem_registros = filtrado.empty
    mapa = _grafico_mapa_home(filtrado, filtros) if not sem_registros else None
    contexto.update(
        {
            "cartoes": _preparar_cartoes_home(filtrado, periodos),
            "grafico_mensal": _figura_div(
                _grafico_evolucao_home(filtrado, periodos),
                config=CONFIG_GRAFICO_HOME,
            )
            if not sem_registros
            else None,
            "grafico_mapa": _figura_div(mapa, config=CONFIG_GRAFICO_HOME)
            if mapa is not None
            else None,
            "grafico_causas": _figura_div(
                _grafico_causas_home(filtrado),
                config=CONFIG_GRAFICO_HOME,
            )
            if not sem_registros
            else None,
            "grafico_classificacao": _figura_div(
                _grafico_classificacao_home(filtrado),
                config=CONFIG_GRAFICO_HOME,
            )
            if not sem_registros
            else None,
            "grafico_ranking": _figura_div(
                _grafico_ranking_home(filtrado, filtros),
                config=CONFIG_GRAFICO_HOME,
            )
            if not sem_registros
            else None,
            "titulo_ranking": "Top 5 BRs" if filtros["uf"] else "Top 5 UFs",
            "mensagem_sem_registros": (
                "" if not sem_registros else "Sem registros para os filtros escolhidos"
            ),
            "mensagem_sem_coordenadas": (
                not sem_registros and mapa is None
            ),
        }
    )
    return render(request, "painel/home.html", contexto)


def painel(request):
    df = carregar_dados()
    filtros = ler_filtros(request)
    filtrado = aplicar_filtros(df, filtros)
    periodos = _periodos_filtrados(df, filtros)

    contexto = _contexto_comum(request, df, filtros, filtrado, "painel")
    contexto["kpis"] = _preparar_kpis(filtrado)
    if filtrado.empty:
        contexto.update(
            {
                "graficos": {},
                "mensagem_sem_registros": "Sem registros para os filtros escolhidos",
                "tabela_trechos": [],
                "tabela_municipios": [],
            }
        )
    else:
        tabela_trechos, tabela_municipios = _preparar_tabelas(filtrado)
        contexto.update(
            {
                "graficos": _gerar_graficos(filtrado, periodos, filtros),
                "mensagem_sem_registros": "",
                "tabela_trechos": tabela_trechos,
                "tabela_municipios": tabela_municipios,
            }
        )
    return render(request, "painel/painel.html", contexto)


def indicador(request, slug):
    if slug not in INDICADORES:
        raise Http404("Indicador não encontrado.")

    df = carregar_dados()
    filtros = ler_filtros(request)
    filtrado = aplicar_filtros(df, filtros)
    indicador_info = INDICADORES[slug]
    periodos = _periodos_filtrados(df, filtros)
    contexto = _contexto_comum(request, df, filtros, filtrado, slug)

    if filtrado.empty:
        graficos = {}
        tabela_trechos, tabela_municipios = [], []
        mensagem_sem_registros = "Sem registros para os filtros escolhidos"
    else:
        coluna_ranking = "br" if filtros["uf"] else "uf"
        nome_ranking = "BR" if filtros["uf"] else "UF"
        mapa = _grafico_mapa(filtrado, filtros)
        graficos = {
            "mensal": _figura_div(
                _grafico_mensal_indicador(filtrado, periodos, slug)
            ),
            "causas": _figura_div(
                _grafico_barras_indicador(
                    filtrado,
                    "causa_acidente",
                    slug,
                    f"Top 10 causas · {indicador_info['nome']}",
                )
            ),
            "ranking": _figura_div(
                _grafico_barras_indicador(
                    filtrado,
                    coluna_ranking,
                    slug,
                    f"Ranking por {nome_ranking} · {indicador_info['nome']}",
                    limite=None,
                )
            ),
            "calor": _figura_div(_grafico_calor_indicador(filtrado, slug, filtros)),
            "mapa": _figura_div(mapa) if mapa is not None else None,
        }
        tabela_trechos, tabela_municipios = _tabelas_indicador(filtrado, slug)
        mensagem_sem_registros = ""

    valor_total = calcular_kpi(filtrado, slug)
    contexto.update(
        {
            "indicador": indicador_info,
            "slug": slug,
            "valor_total": _formatar_kpi(slug, valor_total),
            "comparacao": _comparar_trimestres(df, filtros, slug),
            "graficos": graficos,
            "tabela_trechos": tabela_trechos,
            "tabela_municipios": tabela_municipios,
            "mensagem_sem_registros": mensagem_sem_registros,
            "periodo_comparacao_nota": (
                "A comparação mantém os demais filtros; o intervalo mensal selecionado "
                "não altera os trimestres fixos."
            ),
        }
    )
    return render(request, "painel/indicador.html", contexto)


def risco(request):
    df = carregar_dados()
    filtros = ler_filtros(request)
    filtrado = aplicar_filtros(df, filtros)
    contexto = _contexto_comum(request, df, filtros, filtrado, "risco")
    contexto["cartoes_risco"] = _preparar_cartoes_risco(filtrado, df, filtros)
    contexto["tabela_ups"] = _preparar_tabela_ups(filtrado)
    contexto["mensagem_sem_registros"] = (
        "Sem registros para os filtros escolhidos" if filtrado.empty else ""
    )

    if filtrado.empty:
        contexto["graficos_risco"] = {}
        contexto["mensagem_mapa"] = (
            "Sem acidentes graves para os filtros escolhidos"
        )
    else:
        dados_risco = _adicionar_ups(filtrado)
        mapa = _grafico_mapa_risco(dados_risco, filtros)
        grafico_causas = _grafico_risco_causas(filtrado, filtros)
        grafico_tipos = _grafico_risco_barras(filtrado, "tipo_acidente")
        grafico_clima = _grafico_risco_barras(
            filtrado, "condicao_metereologica"
        )
        grafico_fase = _grafico_risco_barras(filtrado, "fase_dia")
        contexto["graficos_risco"] = {
            "causas": _figura_div(grafico_causas)
            if grafico_causas is not None
            else None,
            "tipos": _figura_div(grafico_tipos) if grafico_tipos is not None else None,
            "horas": _figura_div(_grafico_risco_horas(filtrado)),
            "clima": _figura_div(grafico_clima) if grafico_clima is not None else None,
            "fase": _figura_div(grafico_fase) if grafico_fase is not None else None,
            "mapa": _figura_div(mapa) if mapa is not None else None,
        }
        contexto["mensagem_mapa"] = (
            "Sem acidentes graves para os filtros escolhidos"
        )

    return render(request, "painel/risco.html", contexto)


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
