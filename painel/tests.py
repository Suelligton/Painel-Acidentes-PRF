from unittest.mock import patch

import pandas as pd
from django.test import Client, SimpleTestCase

from .dados import calcular_kpi, limpar
from .views import (
    CONFIG_GRAFICO_HOME,
    _figura_div,
    _grafico_barras_indicador,
    _grafico_mapa,
    _preparar_cartoes_home,
)


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

    def test_mapa_ignora_coordenadas_vazias_ou_invalidas(self):
        dados_sem_pontos_validos = pd.DataFrame(
            {
                "latitude": [None, float("inf")],
                "longitude": [None, 0],
            }
        )
        self.assertIsNone(_grafico_mapa(dados_sem_pontos_validos))

    def test_mapa_usa_centro_escala_legenda_e_hover_localizados(self):
        dados_mapa = pd.concat(
            [
                self.dados,
                self.dados.iloc[[1]].assign(
                    classificacao_acidente="Sem Vítimas"
                ),
            ],
            ignore_index=True,
        )
        figura = _grafico_mapa(dados_mapa)

        self.assertEqual(figura.layout.map.style, "carto-positron")
        self.assertAlmostEqual(
            figura.layout.map.center.lat, dados_mapa["latitude"].mean()
        )
        self.assertAlmostEqual(
            figura.layout.map.center.lon, dados_mapa["longitude"].mean()
        )
        self.assertEqual(figura.layout.map.zoom, 3.3)
        self.assertEqual(
            [traco.name for traco in figura.data],
            ["Com Vítimas Fatais", "Com Vítimas Feridas", "Sem Vítimas"],
        )
        self.assertEqual(figura.layout.legend.title.text, "Classificação")
        hovertemplate = figura.data[0].hovertemplate
        self.assertIn("Data e hora:", hovertemplate)
        self.assertIn("Mortos:", hovertemplate)
        self.assertIn("<extra></extra>", hovertemplate)
        self.assertIn("BR-230, km 146,1", [linha[0] for linha in figura.data[0].customdata])

        self.assertEqual(_grafico_mapa(dados_mapa, {"uf": "TO"}).layout.map.zoom, 6)
        self.assertEqual(
            _grafico_mapa(
                dados_mapa,
                {"uf": "TO", "municipio": "ARAGUAINA"},
            ).layout.map.zoom,
            9,
        )

    def test_cartoes_comparam_ultimo_mes_com_o_anterior(self):
        cartoes = {
            cartao["chave"]: cartao
            for cartao in _preparar_cartoes_home(
                self.dados,
                ["2026-01", "2026-02"],
            )
        }

        self.assertEqual(cartoes["acidentes"]["variacao"], "0,0%")
        self.assertEqual(cartoes["mortos"]["variacao"], "-100,0%")
        self.assertEqual(cartoes["mortos"]["tipo_variacao"], "melhorou")
        self.assertEqual(cartoes["gravidade"]["variacao"], "-100,0%")
        self.assertEqual(cartoes["feridos_graves"]["variacao"], "Novo")
        self.assertEqual(cartoes["feridos_graves"]["tipo_variacao"], "piorou")
        self.assertIn("plotly-graph-div", cartoes["mortos"]["sparkline"])

    def test_barras_quebram_rotulos_sem_perder_nome_no_hover(self):
        dados_barras = pd.concat(
            [
                self.dados.iloc[[0]].assign(
                    causa_acidente=(
                        f"Causa extensa numero {indice} com descrição completa"
                    )
                )
                for indice in range(10)
            ],
            ignore_index=True,
        )
        figura = _grafico_barras_indicador(
            dados_barras,
            "causa_acidente",
            "acidentes",
            "Top causas",
        )

        rotulos = figura.data[0].y
        self.assertTrue(any("<br>" in rotulo for rotulo in rotulos))
        self.assertTrue(
            all(
                len(linha) <= 28
                for rotulo in rotulos
                for linha in rotulo.split("<br>")
            )
        )
        self.assertIn(
            "Causa extensa numero 0 com descrição completa",
            figura.data[0].customdata[:, 0],
        )
        self.assertIn("<extra></extra>", figura.data[0].hovertemplate)
        self.assertGreater(figura.layout.height, 300)
        self.assertTrue(figura.layout.yaxis.automargin)

    def test_graficos_da_home_podem_ocultar_barra_de_ferramentas(self):
        figura = _grafico_barras_indicador(
            self.dados, "causa_acidente", "acidentes", "Top causas"
        )
        div = _figura_div(figura, config=CONFIG_GRAFICO_HOME)

        self.assertIn('"displayModeBar": false', div)


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

    @patch("painel.views.carregar_dados")
    def test_filtros_sem_registros_mostram_mensagem_sem_quebrar(self, carregar_dados):
        carregar_dados.return_value = limpar(criar_dados_brutos())
        query = "?uf=TO&causa=Condutor+dormindo"

        for caminho in ("/", "/painel/", "/indicador/mortos/"):
            with self.subTest(caminho=caminho):
                resposta = self.client.get(f"{caminho}{query}")
                self.assertContains(
                    resposta,
                    "Sem registros para os filtros escolhidos",
                    status_code=200,
                )
