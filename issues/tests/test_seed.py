"""Comando seed_demo, que monta os dados da apresentação."""
import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from issues.management.commands import seed_demo
from issues.models import Issue, Municipio, Report, Vote

from .conftest import box


@pytest.fixture
def estado_rj(db):
    # um "município" cobrindo toda a região dos pontos de exemplo
    return Municipio.objects.create(name='RJ', codigo_ibge='3300000', boundary=box(-44.0, -23.1, -42.9, -22.4))


def test_fails_without_municipios(db):
    with pytest.raises(CommandError, match='load_municipios'):
        call_command('seed_demo')


def test_creates_everything(estado_rj):
    call_command('seed_demo')

    assert Issue.objects.count() == len(seed_demo.ISSUES)
    expected_votes = sum(len(voters) for *_, voters in seed_demo.ISSUES)
    assert Vote.objects.filter(is_active=True).count() == expected_votes
    assert Report.objects.filter(resolved=False).count() == 1


def test_logins_work(estado_rj):
    call_command('seed_demo')

    admin = authenticate(username=seed_demo.ADMIN[0], password=seed_demo.ADMIN[1])
    assert admin is not None and admin.is_superuser
    moderador = authenticate(username=seed_demo.MODERADOR, password=seed_demo.DEMO_PASSWORD)
    assert moderador.groups.filter(name='Moderadores').exists()
    for username in seed_demo.CIDADAOS:
        assert authenticate(username=username, password=seed_demo.DEMO_PASSWORD) is not None


def test_is_idempotent(estado_rj):
    call_command('seed_demo')
    counts = (User.objects.count(), Issue.all_objects.count(), Vote.objects.count(), Report.objects.count())
    call_command('seed_demo')
    assert counts == (User.objects.count(), Issue.all_objects.count(), Vote.objects.count(), Report.objects.count())


def test_does_not_reset_changed_passwords(estado_rj):
    call_command('seed_demo')
    ana = User.objects.get(username='ana')
    ana.set_password('nova-senha-123')
    ana.save()
    call_command('seed_demo')
    assert authenticate(username='ana', password='nova-senha-123') is not None


def test_chain_is_intact_after_seed(estado_rj):
    call_command('seed_demo')
    call_command('seed_demo')
    call_command('verify_chain')


def test_points_outside_municipios_are_skipped(db, capsys):
    # só cobre o centro do Rio: os outros pontos ficam de fora
    Municipio.objects.create(name='Centro', codigo_ibge='3300001', boundary=box(-43.20, -22.95, -43.15, -22.88))
    call_command('seed_demo')
    assert list(Issue.objects.values_list('title', flat=True)) == ['Buraco grande na Av. Rio Branco']
    assert 'Pulando' in capsys.readouterr().out


def test_issues_land_in_the_right_municipio(db):
    rio = Municipio.objects.create(name='Rio', codigo_ibge='1', boundary=box(-43.8, -23.1, -43.13, -22.75))
    niteroi = Municipio.objects.create(name='Niterói', codigo_ibge='2', boundary=box(-43.13, -23.0, -42.95, -22.85))
    call_command('seed_demo')
    assert Issue.objects.get(title='Lixo acumulado em Icaraí').municipio == niteroi
    assert Issue.objects.get(title='Calçada quebrada na Tijuca').municipio == rio
