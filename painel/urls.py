from django.urls import path

from . import views


urlpatterns = [
    path("painel/", views.painel, name="painel"),
    path("exportar/", views.exportar_csv, name="exportar_csv"),
    path("plotly.js", views.plotly_js, name="plotly_js"),
]
