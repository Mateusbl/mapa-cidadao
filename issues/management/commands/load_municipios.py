import json

import requests
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand

from issues.models import Municipio

MALHAS_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/RJ"
    "?formato=application/vnd.geo+json&resolucao=2&intrarregiao=municipio"
)
LOCALIDADES_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/RJ/municipios"


def to_multipolygon(geom):
    # make_valid pode devolver Polygon, MultiPolygon ou GeometryCollection com linhas soltas
    if geom.geom_type == "Polygon":
        return MultiPolygon(geom)
    if geom.geom_type == "MultiPolygon":
        return geom
    polygons = []
    for part in geom:
        if part.geom_type == "Polygon":
            polygons.append(part)
        elif part.geom_type == "MultiPolygon":
            polygons.extend(part)
    return MultiPolygon(polygons, srid=geom.srid)


class Command(BaseCommand):
    help = "Carrega os municípios do RJ (nome + geometria) a partir das APIs do IBGE"

    def handle(self, *args, **options):
        self.stdout.write("Buscando nomes dos municípios...")
        nomes_response = requests.get(LOCALIDADES_URL, timeout=30)
        nomes_response.raise_for_status()
        localidades = nomes_response.json()

        # monta um dicionário código -> nome, pra cruzar com a malha depois
        nomes_por_codigo = {str(m["id"]): m["nome"] for m in localidades}

        self.stdout.write("Buscando geometrias na API de malhas...")
        malha_response = requests.get(MALHAS_URL, timeout=30)
        malha_response.raise_for_status()
        geojson = malha_response.json()

        features = geojson.get("features", [])
        self.stdout.write(f"Recebidos {len(features)} municípios (geometria).")

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for feature in features:
            properties = feature.get("properties", {})
            geometry = feature.get("geometry")

            codigo_ibge = str(properties.get("codarea", ""))
            name = nomes_por_codigo.get(codigo_ibge)

            if not codigo_ibge or not geometry or not name:
                self.stdout.write(self.style.WARNING(
                    f"Pulando: código={codigo_ibge}, nome_encontrado={name}"
                ))
                skipped_count += 1
                continue

            geom = GEOSGeometry(json.dumps(geometry))
            if not geom.valid:
                # geometria inválida faz o boundary__contains falhar sem erro nenhum
                self.stdout.write(self.style.WARNING(f"Corrigindo geometria inválida de {name}: {geom.valid_reason}"))
                geom = to_multipolygon(geom.make_valid())
            else:
                geom = to_multipolygon(geom)

            obj, created = Municipio.objects.update_or_create(
                codigo_ibge=codigo_ibge,
                defaults={"name": name, "boundary": geom},
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Concluído: {created_count} criados, {updated_count} atualizados, {skipped_count} pulados."
        ))
