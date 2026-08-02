from django.core.management.base import BaseCommand
from issues.models import Vote


class Command(BaseCommand):
    help = 'Verifica a integridade da cadeia de hashes dos votos'

    def handle(self, *args, **options):
        votes = Vote.objects.order_by('id')
        expected_previous = ''
        broken = []

        for vote in votes:
            if vote.previous_hash != expected_previous:
                broken.append(vote.id)
            recalculated = vote.compute_hash()
            if recalculated != vote.record_hash:
                broken.append(vote.id)
            expected_previous = vote.record_hash

        if broken:
            self.stdout.write(self.style.ERROR(f'Cadeia quebrada nos votos: {broken}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Cadeia íntegra — {votes.count()} votos verificados.'))
