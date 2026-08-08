from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('issues', '0009_fix_vote_trigger_allow_revocation'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION prevent_vote_modification()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF TG_OP = 'DELETE' THEN
                        RAISE EXCEPTION 'Votes são append-only. Delete não é permitido.';
                    END IF;

                    IF OLD.issue_id != NEW.issue_id
                       OR OLD.user_id != NEW.user_id
                       OR OLD.created_at != NEW.created_at
                       OR OLD.record_hash != NEW.record_hash
                       OR OLD.previous_hash != NEW.previous_hash THEN
                        RAISE EXCEPTION 'Votes são append-only. Apenas revogação (is_active/revoked_at/revoked_reason) é permitida.';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;

                DROP TRIGGER IF EXISTS block_vote_delete ON issues_vote;
                CREATE TRIGGER block_vote_delete
                    BEFORE DELETE ON issues_vote
                    FOR EACH ROW EXECUTE FUNCTION prevent_vote_modification();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS block_vote_delete ON issues_vote;
            """,
        ),
    ]
