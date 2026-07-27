# Django Project

Application Django basée sur une architecture Docker, utilisant PostgreSQL et Django Admin, prête pour un déploiement en production derrière Traefik.

## Stack

- Django 5.x
- PostgreSQL 16
- Django Admin (Unfold)
- Docker & Docker Compose
- Gunicorn + WhiteNoise
- Cloudflare R2 (compatible S3) via `django-storages` pour les fichiers médias

---

## Démarrage en développement

Créer le fichier d'environnement puis lancer les conteneurs :

```bash
cp .env.example .env
docker compose up --build
```

En environnement de développement, Docker Compose remplace automatiquement Gunicorn par `runserver` afin de bénéficier du rechargement automatique du code.

Accéder à l'administration :

```
http://localhost:8000/admin/
```

Créer un super-utilisateur :

```bash
docker compose exec web python manage.py createsuperuser
```

---

## Déploiement en production

Avant le déploiement :

```bash
cp .env.example .env
```

Configurer ensuite les principales variables d'environnement :

- `DJANGO_SETTINGS_MODULE=config.settings.production`
- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_USE_HTTPS=true`
- `DOCKER_IMAGE`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `TRAEFIK_HOST`
- `TRAEFIK_NETWORK`
- `TRAEFIK_ENTRYPOINT`
- `TRAEFIK_CERT_RESOLVER`

Puis lancer le déploiement :

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

L'application est prévue pour fonctionner derrière un reverse proxy Traefik. Le conteneur Django n'expose donc aucun port directement sur l'hôte.

---

## Variables d'environnement essentielles

En production, les variables suivantes sont indispensables :

- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `TRAEFIK_HOST`
- `TRAEFIK_NETWORK`

### Alertes Telegram (erreurs 500)

Un middleware remonte automatiquement les erreurs serveur sur Telegram. Pour l'activer (ou réutiliser le même modèle sur une autre app), configurer :

| Variable | Description |
| -------- | ----------- |
| `APP_NAME` | Nom de l'application affiché dans chaque alerte (ex. `Cargo System`) |
| `TELEGRAM_BOT_TOKEN` | Token du bot Telegram (via [@BotFather](https://t.me/BotFather)) |
| `TELEGRAM_CHAT_ID` | ID du chat / canal qui reçoit les alertes |
| `TELEGRAM_NOTIFY_ENABLED` | `true` / `false` (défaut : `true` si token + chat_id sont présents) |

Chaque notification inclut le nom de l'app, un horodatage clair, la requête, l'exception, et l'email de l'utilisateur authentifié lorsqu'il est disponible.

---

## Stockage des médias

Le projet prend en charge deux modes de stockage :

- **Local** (`USE_R2=false`) : les fichiers sont enregistrés dans le dossier `media/`.
- **Cloudflare R2** (`USE_R2=true`) : les fichiers sont stockés dans un bucket R2 via les variables d'environnement `AWS_*`.

---

## Organisation des paramètres

| Module                       | Description                       |
| ---------------------------- | --------------------------------- |
| `config.settings.local`      | Développement hors Docker         |
| `config.settings.docker`     | Développement avec Docker Compose |
| `config.settings.production` | Configuration de production       |

---

## Commandes utiles

Créer les migrations :

```bash
docker compose exec web python manage.py makemigrations
```

Appliquer les migrations :

```bash
docker compose exec web python manage.py migrate
```

Ouvrir un shell Django :

```bash
docker compose exec web python manage.py shell
```

Collecter les fichiers statiques :

```bash
docker compose exec web python manage.py collectstatic
```

---

## Structure du projet

```
.
├── config/
├── apps/
├── static/
├── media/
├── docker-compose.yml
├── docker-compose.prod.yml
├── Dockerfile
├── .env.example
└── README.md
```

---

## Licence

À compléter selon les besoins du projet.
