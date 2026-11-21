import pandas as pd


ARQUIVO = "data/base.csv"


def carregar_dados():
    try:
        return pd.read_csv(ARQUIVO, sep=";", encoding="latin-1")
    except (UnicodeDecodeError, pd.errors.ParserError):
        print("Falha ao ler com latin-1; tentando novamente com utf-8.")
        return pd.read_csv(ARQUIVO, sep=";", encoding="utf-8")


def main():
    df = carregar_dados()

    for coluna in ("km", "latitude", "longitude"):
        if coluna in df.columns:
            valores = df[coluna].astype("string").str.replace(",", ".", regex=False)
            df[coluna] = pd.to_numeric(valores, errors="coerce")

    if "data_inversa" in df.columns:
        df["data_inversa"] = pd.to_datetime(
            df["data_inversa"], format="%Y-%m-%d", errors="coerce"
        )

    print("=== Dimensões ===")
    print(f"Linhas: {len(df)}")
    print(f"Colunas: {len(df.columns)}")

    print("\n=== Colunas e tipos ===")
    print(df.dtypes.to_string())

    print("\n=== Valores nulos por coluna ===")
    nulos = df.isna().sum()
    percentual_nulos = (nulos / len(df) * 100) if len(df) else nulos.astype(float)
    resumo_nulos = pd.DataFrame(
        {"quantidade": nulos, "percentual": percentual_nulos}
    )
    print(resumo_nulos.to_string(float_format=lambda valor: f"{valor:.4f}%"))

    colunas_texto = df.select_dtypes(
        include=["object", "string", "category"]
    ).columns
    print("\n=== Colunas de texto: valores únicos e 15 mais frequentes ===")
    for coluna in colunas_texto:
        print(f"\n{coluna}: {df[coluna].nunique(dropna=True)} valores únicos")
        print(df[coluna].value_counts(dropna=True).head(15).to_string())

    colunas_numericas = df.select_dtypes(include="number").columns
    print("\n=== Colunas numéricas: soma, mínimo, máximo e média ===")
    for coluna in colunas_numericas:
        serie = df[coluna]
        print(
            f"{coluna}: soma={serie.sum()}, mínimo={serie.min()}, "
            f"máximo={serie.max()}, média={serie.mean()}"
        )

    colunas_data = df.select_dtypes(include=["datetime", "datetimetz"]).columns
    print("\n=== Colunas de data: data mínima e máxima ===")
    for coluna in colunas_data:
        print(f"{coluna}: mínima={df[coluna].min()}, máxima={df[coluna].max()}")

    print("\n=== Cinco primeiras linhas ===")
    print(df.head().to_string(index=False))


if __name__ == "__main__":
    main()
