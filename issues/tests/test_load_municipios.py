"""load_municipios, com as APIs do IBGE simuladas."""
import json

import pytest
from django.contrib.gis.geos import Point
from django.core.management import call_command

from issues.management.commands import load_municipios
from issues.models import Municipio

SQUARE = [[-43.5, -23.0], [-43.5, -22.8], [-43.1, -22.8], [-43.1, -23.0], [-43.5, -23.0]]
# "gravata": o anel se cruza no meio, geometria inválida
BOWTIE = [[-42.9, -22.9], [-42.7, -22.7], [-42.7, -22.9], [-42.9, -22.7], [-42.9, -22.9]]


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


@pytest.fixture
def fake_ibge(monkeypatch):
    nomes = [{'id': 1, 'nome': 'Quadrado'}, {'id': 2, 'nome': 'Gravata'}]
    malha = {'features': [
        {'properties': {'codarea': '1'}, 'geometry': {'type': 'Polygon', 'coordinates': [SQUARE]}},
        {'properties': {'codarea': '2'}, 'geometry': {'type': 'Polygon', 'coordinates': [BOWTIE]}},
        {'properties': {'codarea': '3'}, 'geometry': {'type': 'Polygon', 'coordinates': [SQUARE]}},  # sem nome
    ]}

    def fake_get(url, timeout):
        return FakeResponse(nomes if url == load_municipios.LOCALIDADES_URL else malha)

    monkeypatch.setattr(load_municipios.requests, 'get', fake_get)


def test_loads_municipios(db, fake_ibge):
    call_command('load_municipios')
    assert set(Municipio.objects.values_list('name', flat=True)) == {'Quadrado', 'Gravata'}
    assert Municipio.objects.filter(boundary__contains=Point(-43.3, -22.9)).get().name == 'Quadrado'


def test_invalid_geometry_is_fixed(db, fake_ibge):
    call_command('load_municipios')
    gravata = Municipio.objects.get(name='Gravata')
    assert gravata.boundary.valid
    # o ponto dentro de um dos "laços" da gravata tem que ser encontrado
    assert Municipio.objects.filter(boundary__contains=Point(-42.85, -22.8)).get() == gravata


def test_running_twice_updates(db, fake_ibge):
    call_command('load_municipios')
    call_command('load_municipios')
    assert Municipio.objects.count() == 2
