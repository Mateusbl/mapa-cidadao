import pytest
from django.contrib.auth.models import Group, User
from django.contrib.gis.geos import MultiPolygon, Point, Polygon

from issues.models import Issue, Municipio


def box(min_lng, min_lat, max_lng, max_lat):
    return MultiPolygon(Polygon((
        (min_lng, min_lat), (min_lng, max_lat), (max_lng, max_lat), (max_lng, min_lat), (min_lng, min_lat),
    )))


@pytest.fixture
def municipio(db):
    return Municipio.objects.create(name='Teste', codigo_ibge='0000000', boundary=box(-44.0, -22.5, -43.9, -22.4))


@pytest.fixture
def outro_municipio(db):
    return Municipio.objects.create(name='Vizinho', codigo_ibge='0000001', boundary=box(-43.9, -22.5, -43.8, -22.4))


@pytest.fixture
def user(db):
    return User.objects.create_user(username='testuser', password='senha123')


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username='outro', password='senha123')


@pytest.fixture
def moderador(db):
    user = User.objects.create_user(username='mod', password='senha123')
    user.groups.add(Group.objects.get(name='Moderadores'))
    return user


@pytest.fixture
def issue(db, municipio, user):
    return Issue.objects.create(
        title='Issue de teste',
        description='Descrição',
        location=Point(-43.95, -22.45),
        municipio=municipio,
        created_by=user,
    )
