from django.core.management.base import BaseCommand, CommandError
from issues.models import Issue, Vote


class Command(BaseCommand):
    help = 'Verifica a integridade da cadeia de hashes dos votos e dos issues'

    def handle(self, *args, **options):
        ok = True
        for label, queryset in [('votos', Vote.objects.order_by('id')),
                                ('issues', Issue.all_objects.order_by('id'))]:
            broken = self._check(queryset)
            if broken:
                ok = False
                self.stdout.write(self.style.ERROR(f'Cadeia de {label} quebrada em: {broken}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Cadeia de {label} íntegra — {queryset.count()} verificados.'))
        if not ok:
            raise CommandError('Integridade comprometida.')

    def _check(self, queryset):
        expected_previous = ''
        broken = []
        for record in queryset:
            if record.previous_hash != expected_previous or record.compute_hash() != record.record_hash:
                broken.append(record.id)
            expected_previous = record.record_hash
        return broken
