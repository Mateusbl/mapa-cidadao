# Mapa Cidadão

Plataforma para cidadãos reportarem problemas urbanos no mapa e votarem nos que
consideram prioritários. Votos e issues são protegidos contra adulteração:

- **Hash chain** — cada voto/issue guarda o hash do registro anterior (`verify_chain` detecta quebras).
- **Triggers no PostgreSQL** — votos são append-only (só revogação) e o conteúdo de um issue é imutável (só soft delete).
- **Verifier** — serviço FastAPI separado que recebe cada voto assinado com HMAC e permite conferir o hash depois.
- **Moderação** — denúncias de usuários vão para uma fila; moderadores ocultam (soft delete) ou descartam.

## Como rodar (demo)

```bash
./scripts/demo.sh
```

O script faz tudo de ponta a ponta:

1. cria `.env` e `verifier/.env` (a partir do `.env.example`, com um segredo do Verifier gerado na hora);
2. sobe os containers (`docker compose up -d --build`);
3. espera o `bootstrap`: migrations, municípios do RJ pela API do IBGE (precisa de internet) e a suíte de testes;
4. cria os dados de exemplo (`seed_demo`): usuários, issues espalhados pelo RJ, votos e uma denúncia pendente;
5. confere as cadeias de hash (`verify_chain`) e as páginas principais.

Opções: `--reset` apaga o banco e o histórico do Verifier antes de subir (use se o `verify_chain` acusar
cadeia quebrada por causa de testes antigos), `--no-build` pula o build das imagens.

Logins criados pelo `seed_demo` (só para demo local):

| usuário | senha | papel |
|---|---|---|
| `admin` | `admin12345` | admin + moderação |
| `moderador` | `demo12345` | fila de moderação |
| `ana`, `bruno`, `carla` | `demo12345` | cidadãos |

## Comandos úteis

```bash
docker compose exec app python manage.py seed_demo      # (re)cria os dados de exemplo, é idempotente
docker compose exec app python manage.py verify_chain   # confere a cadeia de hashes dos votos e issues
docker compose exec app pytest issues/tests -v          # testes (inclui integração com o Verifier)
docker compose exec app pytest issues/tests -m "not integration"   # sem precisar do Verifier
```

## Testes

Ficam em `issues/tests/`:

- `test_integrity.py` — hash chain, triggers (append-only / imutável), `verify_chain` detectando adulteração, concorrência
- `test_views.py` — login, criação com validação, votos e revogação, denúncias, moderação e a jornada completa da demo
- `test_admin.py` — o admin não oferece ações que o banco recusaria
- `test_verifier.py` — envio assinado dos votos; integração com o Verifier (assinatura inválida, replay)
- `test_seed.py` / `test_load_municipios.py` — dados da demo e carga dos municípios (IBGE simulado)
