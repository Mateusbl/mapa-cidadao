"""O admin não pode oferecer ações que o banco vai recusar (viraria erro 500 na frente de todo mundo)."""
import pytest
from django.contrib.auth.models import User

from issues.models import Report, Vote


@pytest.fixture
def admin_client(client, db):
    client.force_login(User.objects.create_superuser('root', password='senha123'))
    return client


@pytest.fixture
def vote(issue, user):
    return Vote.objects.create(issue=issue, user=user)


@pytest.mark.parametrize('url', [
    '/admin/issues/issue/', '/admin/issues/vote/', '/admin/issues/report/', '/admin/issues/municipio/',
])
def test_changelists_load(admin_client, issue, url):
    assert admin_client.get(url).status_code == 200


def test_issue_change_page_loads(admin_client, issue):
    assert admin_client.get(f'/admin/issues/issue/{issue.pk}/change/').status_code == 200


def test_issue_content_is_read_only(admin_client, issue):
    resp = admin_client.get(f'/admin/issues/issue/{issue.pk}/change/')
    form = resp.context['adminform'].form
    assert 'title' not in form.fields
    assert 'description' not in form.fields
    assert 'is_deleted' in form.fields


def test_issue_soft_delete_via_admin(admin_client, issue):
    resp = admin_client.post(f'/admin/issues/issue/{issue.pk}/change/', {'is_deleted': 'on'})
    assert resp.status_code == 302
    issue.refresh_from_db()
    assert issue.is_deleted is True


def test_issue_cannot_be_deleted(admin_client, issue):
    assert admin_client.get(f'/admin/issues/issue/{issue.pk}/delete/').status_code == 403


def test_vote_cannot_be_added_or_deleted(admin_client, vote):
    assert admin_client.get('/admin/issues/vote/add/').status_code == 403
    assert admin_client.get(f'/admin/issues/vote/{vote.pk}/delete/').status_code == 403


def test_vote_revocation_via_admin(admin_client, vote):
    resp = admin_client.post(f'/admin/issues/vote/{vote.pk}/change/', {'revoked_reason': 'erro'})
    assert resp.status_code == 302
    vote.refresh_from_db()
    assert vote.is_active is False
    assert vote.revoked_reason == 'erro'


def test_report_admin_change_page(admin_client, issue, user):
    report = Report.objects.create(issue=issue, reported_by=user, reason='spam')
    assert admin_client.get(f'/admin/issues/report/{report.pk}/change/').status_code == 200


def test_hidden_issue_is_listed_and_can_be_restored(admin_client, issue):
    issue.soft_delete()
    resp = admin_client.get('/admin/issues/issue/?is_deleted__exact=1')
    assert 'Issue de teste' in resp.content.decode()

    resp = admin_client.post(f'/admin/issues/issue/{issue.pk}/change/', {})  # desmarca is_deleted
    assert resp.status_code == 302
    issue.refresh_from_db()
    assert issue.is_deleted is False
