# Playground

First steps with Gitlab SaaS

## Wiki-Frontend

Python (FastAPI) + React/TypeScript. Zeigt Markdown aus `content/` an (Navigation, Suche, Graph,
Backlinks) und bearbeitet es per WYSIWYG-Editor. Speichern und Löschen erzeugen einen Merge Request
in GitLab; es wird nie direkt auf den Zielbranch geschrieben.

```
docker compose up --build        # http://localhost:8000
```

Bearbeiten ist nur aktiv, wenn der Server ein GitLab-Token kennt. Variablen (z.B. in einer
gitignorierten `.env`):

| Variable | Bedeutung |
|---|---|
| `GITLAB_TOKEN` | Project Access Token, Scope `api`, Rolle Developer |
| `GITLAB_PROJECT_ID` | Projekt-ID oder Pfad, z.B. `metas-group/data_science/playground` |
| `GITLAB_URL` | Standard `https://gitlab.com` |
| `GITLAB_TARGET_BRANCH` | Standard `main` |
| `GITLAB_CONTENT_PREFIX` | Ordner mit den Seiten im Repo, Standard `content` |

**Sicherheit:** Die Schreib-Endpunkte haben keine Anmeldung; der Name im MR ist eine freie Eingabe.
Wer die App erreicht, kann unter dem Projekt-Token Branches und MRs erzeugen. Compose bindet den
Port deshalb nur an `127.0.0.1`. Die App darf nicht öffentlich oder ohne vorgeschaltete
Authentifizierung (z.B. Reverse Proxy mit SSO) betrieben werden.

Die angezeigten Seiten stammen aus dem Image; nach dem Merge eines MR erscheinen sie erst nach einem
neuen Build.

Hinter einem TLS-aufbrechenden Proxy: CA-Bundle als `certs/ca.pem` ablegen und
`compose.override.example.yaml` nach `compose.override.yaml` kopieren (beides gitignored).

Entwicklung ohne Docker: `cd backend && CONTENT_DIR=../content uv run uvicorn app.main:app --reload`
und `cd frontend && npm run dev`.

## Runner-Verbrauch schätzen

`tools/runner_usage.py` liest Pipelines und Jobs über die GitLab-API und rechnet
Compute-Minuten = Dauer / 60 x Kostenfaktor der Runner-Grösse (Faktoren: GitLab-Doku, "Compute
minutes"; selbst gehostete Runner zählen 0). Nur Standardbibliothek, Python 3.11+.

```
GITLAB_TOKEN=... GITLAB_PROJECT_ID=metas-group/data_science/playground \
  python tools/runner_usage.py --days 30 --quota 10000 \
  --assume "merge_request=40,default_branch=20" --out report.md --csv jobs.csv
```

- `--quota`: Minuten des Abos pro Monat (Standard 10000 = Premium; Free wäre 400).
- `--assume`: erwartete Pipelines pro Monat je Typ (`merge_request`, `default_branch`, `schedule`, `other`); ohne Angabe wird der Zeitraum auf 30 Tage hochgerechnet.
- Token: Scope `read_api`.

In der Pipeline gibt es den Job `report:runner-usage` (manuell auf dem Default-Branch oder per
Pipeline-Schedule). Dafür die CI/CD-Variable `GITLAB_TOKEN` (maskiert) setzen, optional
`RUNNER_QUOTA_MINUTES`. Geplante Pipelines führen nur diesen Job aus.
