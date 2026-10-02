# Mapa Cidadão

Plataforma para cidadãos reportarem problemas urbanos no mapa e votarem nos que
consideram prioritários. Votos e issues são protegidos contra adulteração:

- **Hash chain** — cada voto/issue guarda o hash do registro anterior (`verify_chain` detecta quebras).
- **Triggers no PostgreSQL** — votos são append-only (só revogação) e o conteúdo de um issue é imutável (só soft delete).
- **Verifier** — serviço FastAPI separado que recebe cada voto assinado com HMAC e permite conferir o hash depois.
- **Moderação** — denúncias de usuários vão para uma fila; moderadores ocultam (soft delete) ou descartam.

## Como rodar a demo

### Pré-requisitos

- Docker com Docker Compose (Docker Desktop no Mac/Windows)
- `curl` e `bash` (no Windows, use o WSL)
- Internet: a página carrega o mapa (Leaflet e tiles do OpenStreetMap) da web, e os municípios vêm da API do IBGE

### Subir

```bash
./scripts/demo.sh
```

Cada execução **começa com o banco zerado** e deixa tudo pronto:

1. cria `.env` e `verifier/.env` na primeira vez (a partir do `.env.example`, com um segredo do Verifier gerado na hora);
2. apaga o banco e o histórico do Verifier;
3. sobe os containers (`docker compose up -d --build`);
4. espera o `bootstrap`: migrations, municípios do RJ pelo IBGE e a suíte de testes (para se algum teste falhar);
5. cria os usuários de teste e os dados de exemplo (`seed_demo`): 5 issues pelo RJ, votos e uma denúncia pendente;
6. confere as cadeias de hash (`verify_chain`) e as páginas principais.

A primeira vez demora alguns minutos (build das imagens). Quando terminar, acesse **http://localhost:8000**.

Opções:

| opção | o que faz |
|---|---|
| `--keep` | mantém o banco atual em vez de zerar |
| `--no-build` | não reconstrói as imagens (mais rápido se nada mudou nas dependências) |

### Usuários de teste

| usuário | senha | papel |
|---|---|---|
| `admin` | `admin12345` | admin (`/admin/`) e moderação |
| `moderador` | `demo12345` | fila de moderação (`/moderacao/`) |
| `ana`, `bruno`, `carla` | `demo12345` | cidadãos |

São credenciais só para demo local.

### Roteiro sugerido

1. Abrir a página inicial: mapa com os problemas reportados, filtro por município.
2. Entrar como `ana`, clicar em **Novo Issue**, marcar o local no mapa e enviar.
   Se o ponto não estiver no município escolhido, o sistema avisa em qual ele fica (PostGIS).
3. Votar no issue e depois remover o voto: a revogação é definitiva, porque votos são append-only.
4. Sair e entrar como `moderador`, abrir **Moderação** e ocultar o issue denunciado (soft delete).
5. Mostrar a auditoria:
   ```bash
   docker compose exec app python manage.py verify_chain
   ```

### Se der problema

- **"IBGE indisponível e sem cópia local"**: a API do IBGE não respondeu. Depois da primeira execução que der
  certo, o projeto guarda uma cópia em `.cache/ibge/` e passa a usá-la quando o IBGE estiver fora do ar.
  **Rode o script uma vez com internet boa antes da apresentação.**
- **Mapa não aparece**: sem acesso a `unpkg.com` ou `tile.openstreetmap.org` (rede do local bloqueando).
- **Porta em uso (5432, 8000 ou 9000)**: pare o Postgres ou o outro serviço local que está usando a porta.
- **Ver os logs**: `docker compose logs -f app`.
- **Desligar tudo**: `docker compose down` (ou `docker compose down -v` para apagar também os dados).

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
