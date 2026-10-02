from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('issues', '0012_create_moderadores_group'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION prevent_issue_content_modification()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF TG_OP = 'DELETE' THEN
                        RAISE EXCEPTION 'Conteúdo do Issue é imutável. Delete não é permitido, use soft-delete.';
                    END IF;

                    IF OLD.title IS DISTINCT FROM NEW.title
                       OR OLD.description IS DISTINCT FROM NEW.description
                       OR OLD.location IS DISTINCT FROM NEW.location
                       OR OLD.municipio_id IS DISTINCT FROM NEW.municipio_id
                       OR OLD.created_by_id IS DISTINCT FROM NEW.created_by_id
                       OR OLD.created_at IS DISTINCT FROM NEW.created_at
                       OR OLD.previous_hash IS DISTINCT FROM NEW.previous_hash
                       OR OLD.record_hash IS DISTINCT FROM NEW.record_hash THEN
                        RAISE EXCEPTION 'Conteúdo do Issue é imutável. Apenas soft-delete (is_deleted/deleted_at) é permitido.';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;

                DROP TRIGGER IF EXISTS block_issue_delete ON issues_issue;
                CREATE TRIGGER block_issue_delete
                    BEFORE DELETE ON issues_issue
                    FOR EACH ROW EXECUTE FUNCTION prevent_issue_content_modification();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS block_issue_delete ON issues_issue;
            """,
        ),
    ]
