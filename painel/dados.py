import pickle
from pathlib import Path

import pandas as pd


ARQUIVO_CSV = Path("data/base.csv")
ARQUIVO_CACHE = Path("data/.cache.pkl")

COLUNAS_CONTAGEM = (
    "pessoas",
    "mortos",
    "feridos_leves",
    "feridos_graves",
    "ilesos",
    "ignorados",
    "feridos",
    "veiculos",
)

MESES_NOME = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}

ORDEM_DIA_SEMANA = {
    "segunda-feira": 1,
    "terça-feira": 2,
    "quarta-feira": 3,
    "quinta-feira": 4,
    "sexta-feira": 5,
    "sábado": 6,
    "domingo": 7,
}

INDICADORES = {
    "acidentes": {
        "nome": "Acidentes",
        "descricao": "Quantidade de acidentes registrados.",
        "coluna": "id",
        "tipo": "contagem",
    },
    "mortos": {
        "nome": "Mortos",
        "descricao": "Total de pessoas mortas nos acidentes.",
        "coluna": "mortos",
        "tipo": "soma",
    },
    "feridos_graves": {
        "nome": "Feridos graves",
        "descricao": "Total de pessoas com ferimentos graves.",
        "coluna": "feridos_graves",
        "tipo": "soma",
    },
    "feridos_leves": {
        "nome": "Feridos leves",
        "descricao": "Total de pessoas com ferimentos leves.",
        "coluna": "feridos_leves",
        "tipo": "soma",
    },
    "veiculos": {
        "nome": "Veículos",
        "descricao": "Total de veículos envolvidos nos acidentes.",
        "coluna": "veiculos",
        "tipo": "soma",
    },
    "gravidade": {
        "nome": "Gravidade",
        "descricao": "Mortos por 100 acidentes.",
        "coluna": "mortos",
        "tipo": "razao",
    },
}

_ASSINATURA_MEMORIA = None
_DADOS_EM_MEMORIA = None


def ler_bruto():
    """Lê o arquivo original, sem transformar os valores."""
    # O CSV usa ponto e vírgula para separar colunas e a codificação latin-1.
    return pd.read_csv("data/base.csv", sep=";", encoding="latin-1")


def limpar(df):
    """Prepara uma cópia do DataFrame para os cálculos e gráficos do painel."""
    # Trabalhamos em uma cópia para preservar os dados brutos recebidos.
    df = df.copy()

    # Padronizamos os textos: removemos espaços extras e identificamos ausências.
    colunas_texto = df.select_dtypes(
        include=["object", "string", "category"]
    ).columns
    for coluna in colunas_texto:
        texto = df[coluna].astype("string")
        texto = texto.str.replace(r"\s+", " ", regex=True).str.strip()
        df[coluna] = texto.replace("", pd.NA).fillna("NÃO INFORMADO")

    # O identificador veio como decimal (por exemplo, 742921.0), mas é inteiro.
    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")

    # Convertemos a data e criamos campos simples para filtros e agrupamentos.
    df["data_inversa"] = pd.to_datetime(
        df["data_inversa"], format="%Y-%m-%d", errors="coerce"
    )
    df["data"] = df["data_inversa"]
    df["mes"] = df["data_inversa"].dt.month.astype("Int64")
    df["mes_nome"] = (
        df["mes"].map(MESES_NOME).astype("string").fillna("NÃO INFORMADO")
    )

    # Extraímos a hora inteira (0 a 23) do horário HH:MM:SS.
    horarios = pd.to_datetime(df["horario"], format="%H:%M:%S", errors="coerce")
    df["hora"] = horarios.dt.hour.astype("Int64")

    # Trocamos a vírgula decimal por ponto antes de converter coordenadas e km.
    for coluna in ("km", "latitude", "longitude"):
        valores = df[coluna].astype("string").str.replace(",", ".", regex=False)
        df[coluna] = pd.to_numeric(valores, errors="coerce")

    # A BR também é um número inteiro e pode estar ausente em alguns registros.
    df["br"] = pd.to_numeric(df["br"], errors="coerce").astype("Int64")

    # Campos de quantidade ficam inteiros; valores vazios ou inválidos viram zero.
    for coluna in COLUNAS_CONTAGEM:
        df[coluna] = (
            pd.to_numeric(df[coluna], errors="coerce").fillna(0).astype("int64")
        )

    # Mantemos o nome original do dia e adicionamos a ordem para gráficos.
    df["dia_ordem"] = (
        df["dia_semana"].map(ORDEM_DIA_SEMANA).astype("Int64")
    )

    # Cada trecho é uma faixa de 10 km, iniciada no múltiplo de 10 anterior.
    inicio_faixa = ((df["km"] // 10) * 10).astype("Int64")
    trecho = pd.Series("NÃO INFORMADO", index=df.index, dtype="string")
    tem_localizacao = df["br"].notna() & inicio_faixa.notna()
    inicio_texto = inicio_faixa.loc[tem_localizacao].astype("string")
    fim_texto = (inicio_faixa.loc[tem_localizacao] + 10).astype("string")
    trecho.loc[tem_localizacao] = (
        "BR-"
        + df.loc[tem_localizacao, "br"].astype("string")
        + " km "
        + inicio_texto
        + "-"
        + fim_texto
    )
    df["trecho"] = trecho

    return df


def _assinatura_arquivo():
    """Retorna os metadados usados para saber se o CSV foi alterado."""
    estatisticas = ARQUIVO_CSV.stat()
    return estatisticas.st_mtime_ns, estatisticas.st_size


def carregar_dados():
    """Carrega dados limpos da memória ou do pickle, refazendo o cache se preciso."""
    global _ASSINATURA_MEMORIA, _DADOS_EM_MEMORIA

    # Data e tamanho detectam alterações no CSV sem relê-lo em toda requisição.
    assinatura_atual = _assinatura_arquivo()
    if _ASSINATURA_MEMORIA == assinatura_atual and _DADOS_EM_MEMORIA is not None:
        return _DADOS_EM_MEMORIA

    # Se o cache em disco corresponde ao CSV atual, aproveitamos os dados limpos.
    if ARQUIVO_CACHE.exists():
        with ARQUIVO_CACHE.open("rb") as arquivo:
            cache = pickle.load(arquivo)
        if cache["assinatura"] == assinatura_atual:
            _ASSINATURA_MEMORIA = assinatura_atual
            _DADOS_EM_MEMORIA = cache["dados"]
            return _DADOS_EM_MEMORIA

    # Um CSV novo ou alterado exige uma nova leitura e limpeza.
    dados = limpar(ler_bruto())

    # Gravamos os dados limpos e a assinatura para reutilizá-los na próxima carga.
    with ARQUIVO_CACHE.open("wb") as arquivo:
        pickle.dump(
            {"assinatura": assinatura_atual, "dados": dados},
            arquivo,
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    _ASSINATURA_MEMORIA = assinatura_atual
    _DADOS_EM_MEMORIA = dados
    return _DADOS_EM_MEMORIA


def calcular_kpi(df, chave):
    """Calcula um indicador pelo tipo descrito em INDICADORES."""
    if chave not in INDICADORES:
        raise KeyError(f"Indicador desconhecido: {chave}")

    indicador = INDICADORES[chave]
    if indicador["tipo"] == "contagem":
        return len(df)
    if indicador["tipo"] == "soma":
        return df[indicador["coluna"]].sum()
    if indicador["tipo"] == "razao":
        acidentes = len(df)
        if acidentes == 0:
            return 0
        return df[indicador["coluna"]].sum() / acidentes * 100

    raise ValueError(f"Tipo de indicador não suportado: {indicador['tipo']}")
