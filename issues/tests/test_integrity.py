"""Hash chain, triggers append-only/imutável e verify_chain."""
import threading

import pytest
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone

from issues.models import Issue, Vote


def tamper(table, trigger, column, value, row_id):
    # simula um ataque direto no banco, desligando o trigger de proteção
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger};")
        cursor.execute(f"UPDATE {table} SET {column} = %s WHERE id = %s", [value, row_id])
        cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger};")


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


class TestChainConcurrency:
    def test_concurrent_votes_keep_chain_intact(self, transactional_db, issue):
        users = [User.objects.create_user(username=f'c{n}', password='senha123') for n in range(8)]
        barrier = threading.Barrier(len(users))

        def vote(u):
            barrier.wait()
            Vote.objects.create(issue=issue, user=u)
            connection.close()

        threads = [threading.Thread(target=vote, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        call_command('verify_chain')  # levanta CommandError se a cadeia bifurcou
        assert Vote.objects.count() == len(users)


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

    def test_location_edit_is_blocked(self, issue):
        issue.location = Point(-43.91, -22.41)
        with pytest.raises(Exception, match="imutável"):
            issue.save()

    def test_hard_delete_is_blocked(self, issue):
        with pytest.raises(Exception, match="imutável"):
            Issue.all_objects.filter(id=issue.id).delete()

    def test_description_edit_is_blocked(self, issue):
        issue.description = "Descrição alterada"
        with pytest.raises(Exception, match="imutável"):
            issue.save()


class TestVoteRevocation:
    def test_revocation_is_allowed_by_trigger(self, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)
        vote.is_active = False
        vote.revoked_at = timezone.now()
        vote.revoked_reason = 'mudei de ideia'
        vote.save()
        vote.refresh_from_db()
        assert vote.is_active is False

    def test_revocation_keeps_hash(self, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)
        original = vote.record_hash
        vote.is_active = False
        vote.save()
        vote.refresh_from_db()
        assert vote.record_hash == original == vote.compute_hash()


class TestIssueHashChain:
    def test_issues_chain_to_each_other(self, municipio, user):
        a = Issue.objects.create(title='A', description='a', location=Point(-43.95, -22.45), municipio=municipio, created_by=user)
        b = Issue.objects.create(title='B', description='b', location=Point(-43.95, -22.45), municipio=municipio, created_by=user)
        assert a.previous_hash == ''
        assert b.previous_hash == a.record_hash

    def test_soft_deleted_issue_stays_in_chain(self, municipio, user):
        a = Issue.objects.create(title='A', description='a', location=Point(-43.95, -22.45), municipio=municipio, created_by=user)
        a.soft_delete()
        b = Issue.objects.create(title='B', description='b', location=Point(-43.95, -22.45), municipio=municipio, created_by=user)
        assert b.previous_hash == a.record_hash

    @pytest.mark.parametrize('field, value', [
        ('municipio', None),
        ('created_by', None),
        ('previous_hash', 'f' * 64),
    ])
    def test_other_content_fields_are_blocked(self, issue, outro_municipio, other_user, field, value):
        value = {'municipio': outro_municipio, 'created_by': other_user}.get(field, value)
        setattr(issue, field, value)
        with pytest.raises(Exception, match="imutável"):
            issue.save()


class TestVerifyChainCommand:
    def test_clean_chain_passes(self, issue, user, other_user, capsys):
        Vote.objects.create(issue=issue, user=user)
        Vote.objects.create(issue=issue, user=other_user)
        call_command('verify_chain')
        out = capsys.readouterr().out
        assert 'Cadeia de votos íntegra — 2' in out
        assert 'Cadeia de issues íntegra — 1' in out

    def test_detects_tampered_vote(self, transactional_db, issue, user):
        vote = Vote.objects.create(issue=issue, user=user)
        tamper('issues_vote', 'block_vote_update', 'record_hash', 'adulterado', vote.id)
        with pytest.raises(CommandError):
            call_command('verify_chain')

    def test_detects_tampered_issue_title(self, transactional_db, issue):
        tamper('issues_issue', 'protect_issue_content', 'title', 'Título trocado', issue.id)
        with pytest.raises(CommandError):
            call_command('verify_chain')

    def test_detects_broken_link(self, transactional_db, issue, user, other_user):
        Vote.objects.create(issue=issue, user=user)
        second = Vote.objects.create(issue=issue, user=other_user)
        tamper('issues_vote', 'block_vote_update', 'previous_hash', '0' * 64, second.id)
        with pytest.raises(CommandError):
            call_command('verify_chain')


class TestIssueChainConcurrency:
    def test_concurrent_issues_keep_chain_intact(self, transactional_db, municipio):
        users = [User.objects.create_user(username=f'i{n}', password='senha123') for n in range(8)]
        barrier = threading.Barrier(len(users))

        def create(u):
            barrier.wait()
            Issue.objects.create(title=f'Issue {u.username}', description='d', location=Point(-43.95, -22.45),
                                 municipio=municipio, created_by=u)
            connection.close()

        threads = [threading.Thread(target=create, args=(u,)) for u in users]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        call_command('verify_chain')
        assert Issue.objects.count() == len(users)
