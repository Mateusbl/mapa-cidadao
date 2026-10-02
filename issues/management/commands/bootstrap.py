import subprocess
import time

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import OperationalError

from issues.models import Municipio


class Command(BaseCommand):
    help = "Aplica migrations, carrega municípios (se necessário) e roda os testes"

    def handle(self, *args, **options):
        self.stdout.write("==> Verificando conexão com o banco...")
        self._wait_for_db()

        self.stdout.write("==> Aplicando migrations...")
        subprocess.run(["python", "manage.py", "migrate"], check=True)

        self.stdout.write("==> Verificando municípios...")
        count = Municipio.objects.count()
        if count == 0:
            self.stdout.write("==> Carregando municípios do IBGE...")
            subprocess.run(["python", "manage.py", "load_municipios"], check=True)
        else:
            self.stdout.write(self.style.SUCCESS(f"==> {count} municípios já carregados, pulando."))

        self.stdout.write("==> Rodando testes...")
        result = subprocess.run(["pytest", "issues/tests", "-v"])

        if result.returncode == 0:
            self.stdout.write(self.style.SUCCESS("==> Ambiente pronto e validado."))
        else:
            self.stdout.write(self.style.ERROR("==> Testes falharam. Revise antes de continuar."))

    def _wait_for_db(self, max_attempts=15):
        for attempt in range(max_attempts):
            try:
                connection.ensure_connection()
                self.stdout.write(self.style.SUCCESS("==> Banco pronto."))
                return
            except OperationalError:
                self.stdout.write(f"    banco ainda não respondeu, tentativa {attempt + 1}/{max_attempts}...")
                time.sleep(2)
        raise Exception("Banco não respondeu a tempo.")
