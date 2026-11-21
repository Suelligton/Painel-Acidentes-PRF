import pandas as pd
from django.test import Client, SimpleTestCase

from .dados import calcular_kpi, limpar


def criar_dados_brutos():
    """Cria duas linhas pequenas para testar a limpeza sem ler o CSV real."""
    return pd.DataFrame(
        [
            {
                "id": "742921.0",
                "data_inversa": "2026-01-01",
                "dia_semana": "quinta-feira",
                "horario": "04:04:00",
                "uf": "TO",
                "br": 230,
                "km": "146,1",
                "municipio": "ARAGUAINA",
                "causa_acidente": "Objeto na pista",
                "tipo_acidente": "Tombamento",
                "classificacao_acidente": "Com Vítimas Fatais",
                "fase_dia": "Amanhecer",
                "condicao_metereologica": "Céu Claro",
                "pessoas": 3,
                "mortos": 1,
                "feridos_leves": 0,
                "feridos_graves": 0,
                "ilesos": 1,
                "ignorados": 1,
                "feridos": 0,
                "veiculos": 5,
                "latitude": "-7,291548",
                "longitude": "-48,286252",
            },
            {
                "id": "742942.0",
                "data_inversa": "2026-02-02",
                "dia_semana": "segunda-feira",
                "horario": "18:30:00",
                "uf": "MG",
                "br": 262,
                "km": "12,5",
                "municipio": "  RIO   CASCA  ",
                "causa_acidente": "Condutor dormindo",
                "tipo_acidente": "Colisão frontal",
                "classificacao_acidente": "Com Vítimas Feridas",
                "fase_dia": "Plena Noite",
                "condicao_metereologica": "Chuva",
                "pessoas": 6,
                "mortos": 0,
                "feridos_leves": 1,
                "feridos_graves": 2,
                "ilesos": 1,
                "ignorados": 2,
                "feridos": 3,
                "veiculos": 3,
                "latitude": "-20,0240733",
                "longitude": "-42,7422291",
            },
        ]
    )


class CamadaDadosTests(SimpleTestCase):
    def setUp(self):
        self.dados = limpar(criar_dados_brutos())

    def test_converte_decimais_com_virgula(self):
        self.assertAlmostEqual(self.dados.loc[0, "km"], 146.1)
        self.assertAlmostEqual(self.dados.loc[0, "latitude"], -7.291548)
        self.assertAlmostEqual(self.dados.loc[0, "longitude"], -48.286252)
        self.assertEqual(self.dados.loc[1, "trecho"], "BR-262 km 10-20")

    def test_converte_data_e_cria_campos_de_calendario(self):
        self.assertEqual(self.dados.loc[0, "id"], 742921)
        self.assertEqual(self.dados.loc[0, "data"], pd.Timestamp("2026-01-01"))
        self.assertEqual(self.dados.loc[0, "data_inversa"], pd.Timestamp("2026-01-01"))
        self.assertEqual(self.dados.loc[0, "mes"], 1)
        self.assertEqual(self.dados.loc[0, "mes_nome"], "Jan")
        self.assertEqual(self.dados.loc[0, "hora"], 4)
        self.assertEqual(self.dados.loc[0, "dia_ordem"], 4)
        self.assertEqual(self.dados.loc[1, "municipio"], "RIO CASCA")

    def test_calcula_kpis_e_gravidade_sem_acidentes(self):
        self.assertEqual(calcular_kpi(self.dados, "acidentes"), 2)
        self.assertEqual(calcular_kpi(self.dados, "mortos"), 1)
        self.assertEqual(calcular_kpi(self.dados, "feridos_graves"), 2)
        self.assertEqual(calcular_kpi(self.dados, "feridos_leves"), 1)
        self.assertEqual(calcular_kpi(self.dados, "veiculos"), 8)
        self.assertEqual(calcular_kpi(self.dados, "gravidade"), 50.0)
        self.assertEqual(calcular_kpi(self.dados.iloc[0:0], "gravidade"), 0)


class RotasPainelTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")

    def test_paginas_principais_respondem_com_sucesso(self):
        for caminho in ("/", "/painel/", "/indicador/mortos/"):
            with self.subTest(caminho=caminho):
                resposta = self.client.get(caminho)
                self.assertEqual(resposta.status_code, 200)

    def test_indicador_inexistente_responde_nao_encontrado(self):
        resposta = self.client.get("/indicador/inexistente/")
        self.assertEqual(resposta.status_code, 404)
