#!/usr/bin/env bash
# Sobe o Mapa Cidadão com o banco zerado e deixa tudo pronto pra demo:
# containers, migrations, municípios do IBGE, testes, usuários e dados de
# exemplo e checagem da cadeia de hashes.
#
# Uso: ./scripts/demo.sh [--keep] [--no-build]
#   --keep      mantém o banco atual em vez de começar do zero
#   --no-build  não reconstrói as imagens
#
# Funciona com Docker ou Podman: usa o primeiro que achar entre
# "docker compose", "podman compose" e "docker-compose". Para forçar um:
#   COMPOSE="podman compose" ./scripts/demo.sh
set -euo pipefail

cd "$(dirname "$0")/.."

APP_URL="http://localhost:8000"
WAIT_SECONDS="${WAIT_SECONDS:-600}"
RESET=1
BUILD="--build"

for arg in "$@"; do
    case "$arg" in
        --keep) RESET=0 ;;
        --reset) RESET=1 ;;  # já é o padrão; aceito por compatibilidade
        --no-build) BUILD="" ;;
        -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Opção desconhecida: $arg" >&2; exit 2 ;;
    esac
done

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31mERRO: %s\033[0m\n' "$1" >&2; exit 1; }

if [ -n "${COMPOSE:-}" ]; then
    read -r -a COMPOSE_CMD <<< "$COMPOSE"
elif docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif podman compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(podman compose)
elif docker-compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    fail "nenhum compose encontrado (docker compose, podman compose ou docker-compose)."
fi
compose() { "${COMPOSE_CMD[@]}" "$@"; }

app_running() {
    # nem todo compose (ex.: podman-compose) aceita --status; se não aceitar,
    # assume que está rodando e deixa o timeout pegar o problema
    local out
    out="$(compose ps --status running -q app 2>/dev/null)" || return 0
    [ -n "$out" ]
}
command -v curl >/dev/null || fail "curl não encontrado."

echo "Usando: ${COMPOSE_CMD[*]}"

step "Configurando .env"
if [ ! -f .env ]; then
    secret="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
    sed "s/^VERIFIER_SHARED_SECRET=.*/VERIFIER_SHARED_SECRET=${secret}/" .env.example > .env
    echo "    .env criado a partir do .env.example (segredo do Verifier gerado)"
fi
if [ ! -f verifier/.env ]; then
    grep '^VERIFIER_SHARED_SECRET=' .env > verifier/.env
    echo "    verifier/.env criado com o mesmo segredo"
fi
app_secret="$(grep '^VERIFIER_SHARED_SECRET=' .env || true)"
verifier_secret="$(grep '^VERIFIER_SHARED_SECRET=' verifier/.env || true)"
[ -n "$app_secret" ] || fail "VERIFIER_SHARED_SECRET não está no .env"
[ "$app_secret" = "$verifier_secret" ] || fail "VERIFIER_SHARED_SECRET diferente entre .env e verifier/.env — o Verifier vai rejeitar os votos."

# o container roda como outro usuário (appuser; no Podman rootless, um uid
# mapeado); sem isso ele não consegue gravar a cópia local do IBGE na pasta do
# projeto montada como volume. Só as pastas: os arquivos que o container já
# gravou pertencem ao uid dele e não podem ter o modo mudado daqui
mkdir -p .cache/ibge
chmod a+rwx .cache .cache/ibge 2>/dev/null || true

if [ "$RESET" = 1 ]; then
    step "Zerando banco e histórico do Verifier (use --keep pra manter)"
    # o podman-compose reclama de cada container que ainda não existe; é só ruído
    compose down -v --remove-orphans 2>&1 | grep -viE "no (container|pod) with" || true
fi

step "Subindo containers"
# shellcheck disable=SC2086
compose up -d $BUILD

step "Esperando o bootstrap (migrations, municípios do IBGE e testes)"
# o bootstrap roda antes do runserver; o site só responde quando ele termina
deadline=$((SECONDS + WAIT_SECONDS))
until curl -fs -o /dev/null "$APP_URL/" 2>/dev/null; do
    if ! app_running; then
        compose logs --tail 40 app
        fail "o container da app parou durante o bootstrap (veja o log acima)."
    fi
    [ "$SECONDS" -lt "$deadline" ] || { compose logs --tail 40 app; fail "a app não respondeu em ${WAIT_SECONDS}s."; }
    sleep 3
done

if compose logs app | grep -q "Testes falharam"; then
    compose logs app | grep -E "FAILED|ERROR" | tail -20 || true
    fail "os testes do bootstrap falharam — revise antes de apresentar."
fi
echo "    testes do bootstrap passaram"

step "Criando dados de exemplo"
compose exec -T app python manage.py seed_demo

step "Verificando a integridade das cadeias de hash"
compose exec -T app python manage.py verify_chain \
    || fail "a cadeia de hashes está quebrada neste banco. Rode sem --keep pra começar do zero."

step "Checando as páginas principais"
for path in / /login/ /admin/login/; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$APP_URL$path")"
    [ "$code" = 200 ] || fail "$path respondeu $code"
    echo "    $path OK"
done
curl -fsS -o /dev/null "http://localhost:9000/docs" || fail "Verifier não respondeu em :9000"
echo "    Verifier OK"

printf '\n\033[1;32mTudo pronto!\033[0m Acesse %s\n' "$APP_URL"
cat <<EOF

  Logins de demo:
    admin / admin12345        admin + moderação  ($APP_URL/admin/)
    moderador / demo12345     fila de moderação  ($APP_URL/moderacao/)
    ana, bruno, carla / demo12345   cidadãos

  Roteiro sugerido:
    1. Entrar como ana, ver o mapa e criar um issue clicando no mapa
    2. Votar e revogar o voto (revogar é definitivo: votos são append-only)
    3. Entrar como moderador e ocultar o issue denunciado
    4. ${COMPOSE_CMD[*]} exec app python manage.py verify_chain

EOF
