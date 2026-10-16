# Calendário por matérias

Cada matéria tem um código (ex.: `#math01`). Quem ativa o código vê as datas dele no próprio
calendário. As datas **não são copiadas**: se alguém edita um evento, todos os inscritos veem
a mudança. Qualquer usuário logado pode criar matérias e criar, editar ou apagar eventos; tudo
fica no histórico, e eventos apagados podem ser restaurados.

**Stack:** FastAPI · SQLAlchemy 2 (async) · Alembic · Jinja2 + HTMX · CSS próprio (claro/escuro).

## Rodando

```bash
uv sync                                  # instala dependências
cp .env.example .env                     # configura (troque SECRET_KEY em produção)
uv run alembic upgrade head              # cria/atualiza o banco
uv run uvicorn app.main:app --reload     # http://localhost:8000
uv run pytest                            # testes
```

Depois de mudar `app/models.py`:

```bash
uv run alembic revision --autogenerate -m "descrição"
uv run alembic upgrade head
```

## Configuração (`.env`)

| Variável | Padrão | |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./calendar.db` | Postgres: `postgresql+asyncpg://user:senha@host/db` |
| `SECRET_KEY` | `dev-secret-change-me` | assina os tokens CSRF; **troque em produção** |
| `COOKIE_SECURE` | `false` | `true` em produção (HTTPS) |
| `TIMEZONE` | `America/Sao_Paulo` | fuso em que as datas são digitadas e exibidas |
| `SESSION_DAYS` | `30` | validade da sessão |

## Estrutura

```
app/
  main.py          app, middleware CSRF, tratamento de erros
  models.py        tabelas (datas sempre em UTC)
  schemas.py       validação (Pydantic)
  security.py      argon2, tokens de sessão, CSRF
  services/        regras de negócio (usadas pela API e pelas páginas)
  routers/
    api_*.py       API JSON em /api (documentação em /docs)
    pages.py       páginas HTML e partials HTMX
  templates/       Jinja2
  static/          app.css, app.js, htmx
tests/
```

## API JSON

Login por cookie. Depois do login/cadastro, a resposta traz o header `X-CSRF-Token`, que deve ser
enviado em toda requisição POST/PATCH/DELETE (também disponível em `GET /api/auth/me`).
A documentação interativa fica em `/docs`.
