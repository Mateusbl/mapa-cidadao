"""Fluxos HTTP: login, criação, voto, denúncia, moderação e a jornada completa da demo."""
import json
import math
import re

import pytest
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.management import call_command

from issues.models import Issue, Report, Vote


def map_points(resp):
    match = re.search(r"JSON\.parse\('(.*?)'\)", resp.content.decode())
    # o template usa escapejs; decodifica os \uXXXX de volta pra JSON
    raw = match.group(1).encode().decode('unicode_escape')
    return json.loads(raw)


class TestAuthAndBasics:
    def test_login_required_redirects_to_login_page(self, client, db):
        resp = client.get('/issue/novo/')
        assert resp.status_code == 302
        assert resp.url.startswith('/login/')

    def test_login_redirects_to_issue_list(self, client, user):
        resp = client.post('/login/', {'username': 'testuser', 'password': 'senha123'})
        assert resp.status_code == 302
        assert resp.url == '/'

    def test_vote_via_get_is_rejected(self, client, issue, user):
        client.force_login(user)
        resp = client.get(f'/issue/{issue.pk}/votar/')
        assert resp.status_code == 405
        assert Vote.objects.count() == 0

    def test_vote_via_post_registers(self, client, issue, user):
        client.force_login(user)
        client.post(f'/issue/{issue.pk}/votar/')
        assert Vote.objects.filter(issue=issue, user=user, is_active=True).count() == 1

    @pytest.mark.parametrize('overrides', [
        {'lat': 'abc'},
        {'lat': 'nan'},
        {'lat': '999'},
        {'municipio': 'abc'},
        {'title': 'a' * 201},
        {'lat': '-23.55', 'lng': '-46.63'},  # fora do município
    ])
    def test_invalid_issue_input_is_rejected(self, client, municipio, user, overrides):
        client.force_login(user)
        data = {'title': 't', 'description': 'd', 'municipio': municipio.pk, 'lat': '-22.45', 'lng': '-43.95'}
        data.update(overrides)
        resp = client.post('/issue/novo/', data)
        assert resp.status_code == 200  # volta pro formulário com erro, sem 500
        assert Issue.objects.count() == 0

    def test_valid_issue_is_created(self, client, municipio, user):
        client.force_login(user)
        resp = client.post('/issue/novo/', {
            'title': 't', 'description': 'd', 'municipio': municipio.pk, 'lat': '-22.45', 'lng': '-43.95',
        })
        assert resp.status_code == 302
        assert Issue.objects.count() == 1

    def test_list_with_invalid_filter_does_not_crash(self, client, issue):
        assert client.get('/?municipio=abc').status_code == 200

    def test_moderator_can_hide_issue(self, client, issue, user, moderador):
        report = Report.objects.create(issue=issue, reported_by=user, reason='spam')

        client.force_login(moderador)
        client.post(f'/moderacao/{report.pk}/ocultar/')

        assert Issue.objects.filter(pk=issue.pk).count() == 0
        report.refresh_from_db()
        assert report.resolved is True

    def test_regular_user_cannot_moderate(self, client, issue, user):
        report = Report.objects.create(issue=issue, reported_by=user, reason='spam')
        client.force_login(user)
        client.post(f'/moderacao/{report.pk}/ocultar/')
        assert Issue.objects.filter(pk=issue.pk).count() == 1

    def test_logout_requires_post_and_works(self, client, user):
        client.force_login(user)
        resp = client.post('/logout/')
        assert resp.status_code == 302
        assert '_auth_user_id' not in client.session


class TestIssueList:
    def test_shows_issue_on_map(self, client, issue):
        points = map_points(client.get('/'))
        assert points == [{'lat': -22.45, 'lng': -43.95, 'title': 'Issue de teste', 'url': f'/issue/{issue.pk}/'}]

    def test_filter_by_municipio(self, client, issue, outro_municipio, user):
        Issue.objects.create(title='Vizinho', description='d', location=Point(-43.85, -22.45),
                             municipio=outro_municipio, created_by=user)
        resp = client.get(f'/?municipio={outro_municipio.pk}')
        assert [p['title'] for p in map_points(resp)] == ['Vizinho']

    def test_hidden_issue_not_listed(self, client, issue):
        issue.soft_delete()
        assert map_points(client.get('/')) == []
        assert client.get(f'/issue/{issue.pk}/').status_code == 404

    def test_invalid_point_in_db_does_not_break_map(self, client, issue, municipio, user):
        Issue.objects.create(title='Quebrado', description='d', location=Point(-43.95, math.nan),
                             municipio=municipio, created_by=user)
        resp = client.get('/')
        assert resp.status_code == 200
        assert [p['title'] for p in map_points(resp)] == ['Issue de teste']

    def test_title_with_html_is_escaped(self, client, municipio, user):
        Issue.objects.create(title='<img src=x onerror=alert(1)>', description='d', location=Point(-43.95, -22.45),
                             municipio=municipio, created_by=user)
        html = client.get('/').content.decode()
        assert '<img src=x' not in html
        assert '&lt;img src=x' in html  # lista em HTML
        # o popup do mapa monta o link via DOM (textContent), nunca como HTML
        assert 'link.textContent = point.title' in html
        assert '${point.title}' not in html


class TestMapTiles:
    @pytest.mark.parametrize('url', ['/', '/issue/novo/'])
    def test_maps_use_keyless_osm_tiles(self, client, user, url):
        # os tiles da CARTO passaram a devolver "API KEY REQUIRED" no lugar do mapa
        client.force_login(user)
        html = client.get(url).content.decode()
        assert 'https://tile.openstreetmap.org/{z}/{x}/{y}.png' in html
        assert 'cartocdn' not in html


class TestVoting:
    def test_vote_count_on_detail(self, client, issue, user, other_user):
        Vote.objects.create(issue=issue, user=user)
        Vote.objects.create(issue=issue, user=other_user)
        assert client.get(f'/issue/{issue.pk}/').context['vote_count'] == 2

    def test_second_post_revokes(self, client, issue, user):
        client.force_login(user)
        client.post(f'/issue/{issue.pk}/votar/')
        client.post(f'/issue/{issue.pk}/votar/')
        vote = Vote.objects.get(issue=issue, user=user)
        assert vote.is_active is False
        assert vote.revoked_at is not None

    def test_revoked_vote_cannot_be_reactivated(self, client, issue, user):
        client.force_login(user)
        for _ in range(3):
            client.post(f'/issue/{issue.pk}/votar/')
        assert Vote.objects.filter(issue=issue, user=user).count() == 1
        assert Vote.objects.get(issue=issue, user=user).is_active is False

    def test_detail_shows_button_by_vote_state(self, client, issue, user):
        client.force_login(user)
        assert 'Votar neste issue' in client.get(f'/issue/{issue.pk}/').content.decode()
        client.post(f'/issue/{issue.pk}/votar/')
        assert 'Remover meu voto' in client.get(f'/issue/{issue.pk}/').content.decode()
        client.post(f'/issue/{issue.pk}/votar/')
        html = client.get(f'/issue/{issue.pk}/').content.decode()
        assert 'revogação é definitiva' in html
        assert 'Votar neste issue' not in html

    def test_anonymous_cannot_vote(self, client, issue):
        resp = client.post(f'/issue/{issue.pk}/votar/')
        assert resp.status_code == 302
        assert resp.url.startswith('/login/')
        assert Vote.objects.count() == 0


class TestReports:
    def test_report_is_created(self, client, issue, other_user):
        client.force_login(other_user)
        client.post(f'/issue/{issue.pk}/denunciar/', {'reason': 'spam'})
        report = Report.objects.get(issue=issue)
        assert report.reason == 'spam'
        assert report.resolved is False

    def test_duplicate_report_is_ignored(self, client, issue, other_user):
        client.force_login(other_user)
        client.post(f'/issue/{issue.pk}/denunciar/', {'reason': 'spam'})
        client.post(f'/issue/{issue.pk}/denunciar/', {'reason': 'de novo'})
        assert Report.objects.filter(issue=issue).count() == 1

    def test_report_via_get_is_rejected(self, client, issue, other_user):
        client.force_login(other_user)
        assert client.get(f'/issue/{issue.pk}/denunciar/').status_code == 405


class TestModeration:
    def test_queue_lists_pending_reports(self, client, issue, user, moderador):
        Report.objects.create(issue=issue, reported_by=user, reason='spam')
        client.force_login(moderador)
        resp = client.get('/moderacao/')
        assert resp.status_code == 200
        assert len(resp.context['reports']) == 1

    def test_regular_user_cannot_see_queue(self, client, user):
        client.force_login(user)
        resp = client.get('/moderacao/')
        assert resp.status_code == 302
        assert resp.url == '/'

    def test_superuser_is_moderator(self, client, db):
        admin = User.objects.create_superuser('root', password='senha123')
        client.force_login(admin)
        assert client.get('/moderacao/').status_code == 200

    def test_nav_link_only_for_moderators(self, client, user, moderador):
        client.force_login(user)
        assert '/moderacao/' not in client.get('/').content.decode()
        client.force_login(moderador)
        assert '/moderacao/' in client.get('/').content.decode()

    def test_hiding_resolves_all_reports_of_issue(self, client, issue, user, other_user, moderador):
        r1 = Report.objects.create(issue=issue, reported_by=user, reason='spam')
        Report.objects.create(issue=issue, reported_by=other_user, reason='ofensivo')
        client.force_login(moderador)
        client.post(f'/moderacao/{r1.pk}/ocultar/')
        assert Report.objects.filter(issue=issue, resolved=False).count() == 0
        assert Report.objects.filter(resolved_by=moderador).count() == 2

    def test_dismiss_keeps_issue(self, client, issue, user, moderador):
        report = Report.objects.create(issue=issue, reported_by=user, reason='spam')
        client.force_login(moderador)
        client.post(f'/moderacao/{report.pk}/descartar/')
        report.refresh_from_db()
        assert report.resolved is True
        assert Issue.objects.filter(pk=issue.pk).exists()

    def test_moderation_via_get_is_rejected(self, client, issue, user, moderador):
        report = Report.objects.create(issue=issue, reported_by=user, reason='spam')
        client.force_login(moderador)
        assert client.get(f'/moderacao/{report.pk}/ocultar/').status_code == 405
        assert Issue.objects.filter(pk=issue.pk).exists()


class TestIssueForm:
    def test_wrong_municipio_suggests_the_right_one(self, client, municipio, outro_municipio, user):
        client.force_login(user)
        resp = client.post('/issue/novo/', {
            'title': 't', 'description': 'd', 'municipio': municipio.pk, 'lat': '-22.45', 'lng': '-43.85',
        })
        assert 'fica em Vizinho' in resp.content.decode()

    def test_error_keeps_typed_values(self, client, municipio, user):
        client.force_login(user)
        resp = client.post('/issue/novo/', {
            'title': 'Meu título', 'description': 'Minha descrição', 'municipio': municipio.pk,
            'lat': '-23.55', 'lng': '-46.63',
        })
        html = resp.content.decode()
        assert 'value="Meu título"' in html
        assert 'Minha descrição' in html
        assert 'value="-23.55"' in html


class TestDemoJourney:
    """A jornada da apresentação, ponta a ponta, só pelo HTTP."""

    def test_full_journey(self, client, municipio, moderador, capsys):
        ana = User.objects.create_user('ana', password='senha123')
        bruno = User.objects.create_user('bruno', password='senha123')

        # ana entra e reporta um problema
        resp = client.post('/login/', {'username': 'ana', 'password': 'senha123'})
        assert resp.url == '/'
        resp = client.post('/issue/novo/', {
            'title': 'Buraco', 'description': 'Grande', 'municipio': municipio.pk, 'lat': '-22.45', 'lng': '-43.95',
        })
        issue = Issue.objects.get(title='Buraco')
        assert resp.url == f'/issue/{issue.pk}/'
        assert issue.created_by == ana
        client.post(f'/issue/{issue.pk}/votar/')
        client.post('/logout/')

        # bruno vota e denuncia
        client.force_login(bruno)
        client.post(f'/issue/{issue.pk}/votar/')
        assert client.get(f'/issue/{issue.pk}/').context['vote_count'] == 2
        client.post(f'/issue/{issue.pk}/denunciar/', {'reason': 'duplicado'})

        # o moderador oculta
        client.force_login(moderador)
        report = client.get('/moderacao/').context['reports'][0]
        client.post(f'/moderacao/{report.pk}/ocultar/')
        assert client.get(f'/issue/{issue.pk}/').status_code == 404
        assert map_points(client.get('/')) == []

        # e tudo continua auditável
        call_command('verify_chain')
        out = capsys.readouterr().out
        assert 'Cadeia de votos íntegra — 2' in out
        assert 'Cadeia de issues íntegra — 1' in out
