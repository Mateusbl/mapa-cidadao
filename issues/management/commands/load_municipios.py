import json

import requests
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError

from issues.models import Municipio

MALHAS_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/RJ"
    "?formato=application/vnd.geo+json&resolucao=2&intrarregiao=municipio"
)
LOCALIDADES_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/RJ/municipios"

# cópia local da última resposta boa do IBGE: a demo sobe o banco do zero toda vez,
# então sem isso uma instabilidade na API (ou na internet do local) impede a apresentação
CACHE_DIR = settings.BASE_DIR / ".cache" / "ibge"


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
        localidades = self._fetch(LOCALIDADES_URL, "localidades.json")

        # monta um dicionário código -> nome, pra cruzar com a malha depois
        nomes_por_codigo = {str(m["id"]): m["nome"] for m in localidades}

        self.stdout.write("Buscando geometrias na API de malhas...")
        geojson = self._fetch(MALHAS_URL, "malhas.json")

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

    def _fetch(self, url, cache_name):
        cache_file = CACHE_DIR / cache_name
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            if not cache_file.exists():
                raise CommandError(f"IBGE indisponível e sem cópia local em {cache_file}: {e}")
            self.stdout.write(self.style.WARNING(f"IBGE indisponível ({e.__class__.__name__}), usando a cópia local."))
            return json.loads(cache_file.read_text())

        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data))
        except OSError as e:
            self.stdout.write(self.style.WARNING(f"Não consegui salvar a cópia local do IBGE: {e}"))
        return data
