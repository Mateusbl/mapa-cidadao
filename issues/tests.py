from django.test import TestCase
import pytest
import requests
from django.contrib.auth.models import Group, User
from django.contrib.gis.geos import Point, Polygon, MultiPolygon
from django.db import connection
from issues.models import Issue, Vote, Municipio, Report


# ---------- Fixtures ----------

@pytest.fixture
def municipio(db):
    poly = Polygon(((-44.0, -22.5), (-44.0, -22.4), (-43.9, -22.4), (-43.9, -22.5), (-44.0, -22.5)))
    return Municipio.objects.create(name='Teste', codigo_ibge='0000000', boundary=MultiPolygon(poly))


@pytest.fixture
def user(db):
    return User.objects.create_user(username='testuser', password='senha123')


@pytest.fixture
def issue(db, municipio, user):
    return Issue.objects.create(
        title='Issue de teste',
        description='Descrição',
        location=Point(-43.95, -22.45),
        municipio=municipio,
        created_by=user,
    )


# ---------- Vote: hash chain ----------

class TestVoteHashChain:
    def test_first_vote_has_empty_previous_hash(self, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)
        assert vote.previous_hash == ''
        assert len(vote.record_hash) == 64

    def test_second_vote_chains_to_first(self, db, municipio, user):
        user2 = User.objects.create_user(username='user2', password='senha123')
        issue1 = Issue.objects.create(title='A', description='a', location=Point(0, 0), municipio=municipio, created_by=user)
        issue2 = Issue.objects.create(title='B', description='b', location=Point(0, 0), municipio=municipio, created_by=user)

        vote1 = Vote.objects.create(issue=issue1, user=user)
        vote2 = Vote.objects.create(issue=issue2, user=user2)

        assert vote2.previous_hash == vote1.record_hash

    def test_delete_is_blocked_by_trigger(self, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)
        with pytest.raises(Exception, match="append-only"):
            Vote.objects.filter(id=vote.id).delete()

    def test_update_is_blocked_by_trigger(self, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)
        vote.record_hash = "hash_falso"
        with pytest.raises(Exception, match="append-only"):
            vote.save()

    def test_tampering_detected_by_verify_chain(self, transactional_db, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE issues_vote DISABLE TRIGGER block_vote_update;")
            cursor.execute("UPDATE issues_vote SET record_hash = %s WHERE id = %s", ["adulterado", vote.id])
            cursor.execute("ALTER TABLE issues_vote ENABLE TRIGGER block_vote_update;")

        vote.refresh_from_db()
        assert vote.compute_hash() != vote.record_hash


# ---------- Issue: soft delete + content protection ----------

class TestIssueContentProtection:
    def test_soft_delete_works(self, issue):
        issue.soft_delete()
        assert issue.is_deleted is True
        assert issue.deleted_at is not None

    def test_default_manager_excludes_deleted(self, issue):
        issue.soft_delete()
        assert Issue.objects.filter(id=issue.id).count() == 0
        assert Issue.all_objects.filter(id=issue.id).count() == 1

    def test_title_edit_is_blocked(self, issue):
        issue.title = "Alterado"
        with pytest.raises(Exception, match="imutável"):
            issue.save()

    def test_description_edit_is_blocked(self, issue):
        issue.description = "Descrição alterada"
        with pytest.raises(Exception, match="imutável"):
            issue.save()


# ---------- Verifier: integração (requer o serviço rodando) ----------

@pytest.mark.integration
class TestVerifierIntegration:
    VERIFIER_URL = "http://verifier:9000"

    def test_vote_creation_reaches_verifier(self, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)

        resp = requests.get(f"{self.VERIFIER_URL}/verify/{vote.id}", params={"current_hash": vote.record_hash})
        assert resp.json()["status"] == "OK"

    def test_verifier_detects_tampering(self, transactional_db, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)

        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE issues_vote DISABLE TRIGGER block_vote_update;")
            cursor.execute("UPDATE issues_vote SET record_hash = %s WHERE id = %s", ["hash_falso", vote.id])
            cursor.execute("ALTER TABLE issues_vote ENABLE TRIGGER block_vote_update;")

        resp = requests.get(f"{self.VERIFIER_URL}/verify/{vote.id}", params={"current_hash": "hash_falso"})
        data = resp.json()
        assert data["status"] == "MISMATCH"
        assert data["expected"] == vote.compute_hash()


# ---------- Views: fluxos usados na demo ----------

class TestViews:
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

    def test_invalid_location_does_not_crash(self, client, municipio, user):
        client.force_login(user)
        resp = client.post('/issue/novo/', {
            'title': 't', 'description': 'd', 'municipio': municipio.pk, 'lat': 'abc', 'lng': '-43.2',
        })
        assert resp.status_code == 302
        assert Issue.objects.count() == 0

    def test_moderator_can_hide_issue(self, client, issue, user):
        moderador = User.objects.create_user(username='mod', password='senha123')
        moderador.groups.add(Group.objects.get(name='Moderadores'))
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
