from io import StringIO

import pandas as pd
import plotly.express as px
from django.http import Http404, HttpResponse
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


def _formatar_kpi(chave, valor):
    if INDICADORES[chave]["tipo"] == "razao":
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return _formatar_inteiro(valor)


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


def _rotulo_grupo(valor):
    if isinstance(valor, tuple):
        partes = ["NÃO INFORMADO" if pd.isna(parte) else str(parte) for parte in valor]
        return " / ".join(partes)
    return "NÃO INFORMADO" if pd.isna(valor) else str(valor)


def _grafico_barras_indicador(df, coluna, chave, titulo, limite=10):
    valores = _serie_indicador(df, coluna, chave).sort_values(ascending=False).head(limite)
    valores = valores.sort_values(ascending=True)
    tabela = pd.DataFrame(
        {
            "categoria": [_rotulo_grupo(valor) for valor in valores.index],
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
        title=titulo,
        color_discrete_sequence=[CORES_PMPB["vermelho"]],
        template="plotly_white",
    )
    figura.update_traces(
        texttemplate=f"%{{x:,.{casas_decimais}f}}",
        textposition="inside",
        textfont_color="white",
        cliponaxis=False,
    )
    figura.update_layout(
        xaxis_title=INDICADORES[chave]["nome"],
        yaxis_title="",
        margin={"l": 24, "r": 30, "t": 55, "b": 35},
    )
    return _aplicar_tema(figura)


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


def _grafico_calor_indicador(df, chave):
    valores = _serie_indicador(df, ["dia_semana", "hora"], chave)
    tabela = (
        valores.unstack("hora")
        .reindex(index=DIAS_SEMANA, columns=range(24), fill_value=0)
    )
    texto = ".2f" if INDICADORES[chave]["tipo"] == "razao" else True
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
            {"nome": _rotulo_grupo(trecho), "valor": _formatar_kpi(chave, valor)}
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
    mapa = _grafico_mapa(df, filtros)
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
    contexto.update(
        {
            "cartoes": _preparar_kpis(filtrado, incluir_chave=True),
            "grafico_mensal": (
                _figura_div(_grafico_mensal(filtrado, periodos))
                if not filtrado.empty
                else None
            ),
            "mensagem_sem_registros": (
                "" if not filtrado.empty else "Sem registros para os filtros escolhidos"
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
            "calor": _figura_div(_grafico_calor_indicador(filtrado, slug)),
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
