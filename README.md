# Mapa Cidadão

Plataforma para cidadãos reportarem problemas urbanos no mapa e votarem nos que
consideram prioritários. Votos e issues são protegidos contra adulteração:

- **Hash chain** — cada voto/issue guarda o hash do registro anterior (`verify_chain` detecta quebras).
- **Triggers no PostgreSQL** — votos são append-only (só revogação) e o conteúdo de um issue é imutável (só soft delete).
- **Verifier** — serviço FastAPI separado que recebe cada voto assinado com HMAC e permite conferir o hash depois.
- **Moderação** — denúncias de usuários vão para uma fila; moderadores ocultam (soft delete) ou descartam.

## Como rodar

```bash
cp .env.example .env
cp .env.example verifier/.env   # o mesmo VERIFIER_SHARED_SECRET nos dois
docker compose up --build
```

O comando `bootstrap` aplica as migrations, carrega os municípios do RJ pela API do IBGE
(precisa de internet na primeira vez) e roda os testes. Depois, acesse http://localhost:8000.

Crie um usuário admin (que também pode moderar):

```bash
docker compose exec app python manage.py createsuperuser
```

Para dar permissão de moderação a outro usuário, adicione-o ao grupo **Moderadores** em `/admin/`.

## Comandos úteis

```bash
docker compose exec app python manage.py verify_chain   # confere a cadeia de hashes dos votos
docker compose exec app pytest issues/tests.py -v       # testes (inclui integração com o Verifier)
```
