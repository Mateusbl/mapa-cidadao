from django.contrib.auth.models import Group, User
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError

from issues.models import Issue, Municipio, Report, Vote

# credenciais só pra demo local — nunca usar em produção
DEMO_PASSWORD = 'demo12345'
ADMIN = ('admin', 'admin12345')
MODERADOR = 'moderador'
CIDADAOS = ['ana', 'bruno', 'carla']

# (título, descrição, autor, lat, lng, quem vota)
ISSUES = [
    ('Buraco grande na Av. Rio Branco',
     'Buraco na faixa da direita, perto da Cinelândia. Já causou acidente com moto.',
     'ana', -22.9097, -43.1760, ['ana', 'bruno', 'carla']),
    ('Iluminação apagada em Copacabana',
     'Postes apagados na Av. Nossa Senhora de Copacabana há mais de uma semana.',
     'bruno', -22.9680, -43.1850, ['bruno', 'carla']),
    ('Calçada quebrada na Tijuca',
     'Calçada destruída por raiz de árvore na Rua Conde de Bonfim, difícil passar com carrinho.',
     'carla', -22.9249, -43.2324, ['ana']),
    ('Lixo acumulado em Icaraí',
     'Coleta não passa há dias, lixo espalhado na esquina.',
     'ana', -22.9050, -43.1100, ['carla']),
    ('Semáforo quebrado no centro de Duque de Caxias',
     'Semáforo piscando amarelo o dia todo, cruzamento perigoso.',
     'bruno', -22.7856, -43.3117, []),
]

# issue que fica com uma denúncia pendente, pra mostrar a fila de moderação
REPORTED = ('Calçada quebrada na Tijuca', 'bruno', 'Parece duplicado de outro issue')


class Command(BaseCommand):
    help = 'Cria usuários, issues, votos e uma denúncia de exemplo pra demo (idempotente)'

    def handle(self, *args, **options):
        if not Municipio.objects.exists():
            raise CommandError('Nenhum município carregado. Rode "python manage.py load_municipios" antes.')

        users = self._create_users()

        created = skipped = 0
        for title, description, author, lat, lng, voters in ISSUES:
            point = Point(lng, lat, srid=4326)
            municipio = Municipio.objects.filter(boundary__contains=point).first()
            if municipio is None:
                self.stdout.write(self.style.WARNING(f'Pulando "{title}": ponto fora dos municípios carregados.'))
                skipped += 1
                continue

            issue = Issue.all_objects.filter(title=title).first()
            if issue is None:
                issue = Issue.objects.create(
                    title=title, description=description, location=point,
                    municipio=municipio, created_by=users[author],
                )
                created += 1

            for voter in voters:
                if not Vote.objects.filter(issue=issue, user=users[voter]).exists():
                    Vote.objects.create(issue=issue, user=users[voter])

        title, reporter, reason = REPORTED
        reported_issue = Issue.objects.filter(title=title).first()
        if reported_issue:
            Report.objects.get_or_create(
                issue=reported_issue, reported_by=users[reporter], defaults={'reason': reason},
            )

        self.stdout.write(self.style.SUCCESS(
            f'Demo pronta: {created} issues criados, {skipped} pulados, '
            f'{Issue.objects.count()} issues visíveis, {Vote.objects.filter(is_active=True).count()} votos ativos.'
        ))
        self.stdout.write('Logins (senha):')
        self.stdout.write(f'  {ADMIN[0]} ({ADMIN[1]}) — admin e moderador')
        self.stdout.write(f'  {MODERADOR} ({DEMO_PASSWORD}) — moderador')
        self.stdout.write(f'  {", ".join(CIDADAOS)} ({DEMO_PASSWORD}) — cidadãos')

    def _create_users(self):
        moderadores, _ = Group.objects.get_or_create(name='Moderadores')

        admin = User.objects.filter(username=ADMIN[0]).first()
        if admin is None:
            User.objects.create_superuser(ADMIN[0], password=ADMIN[1])

        users = {}
        for username in [MODERADOR, *CIDADAOS]:
            user = User.objects.filter(username=username).first()
            if user is None:
                user = User.objects.create_user(username, password=DEMO_PASSWORD)
            users[username] = user

        users[MODERADOR].groups.add(moderadores)
        return users
