# French Test App

A spaced-repetition QCM practice app for the HEP Vaud French language proficiency exam (OP001)

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

License: MIT

## Settings

Moved to [settings](https://cookiecutter-django.readthedocs.io/en/latest/1-getting-started/settings.html).

## Basic Commands

### Setting Up Your Users

- To create a **normal user account**, just go to Sign Up and fill out the form. Once you submit it, you'll see a "Verify Your E-mail Address" page. Go to your console to see a simulated email verification message. Copy the link into your browser. Now the user's email should be verified and ready to go.

- To create a **superuser account**, use this command:

      uv run python manage.py createsuperuser

For convenience, you can keep your normal user logged in on Chrome and your superuser logged in on Firefox (or similar), so that you can see how the site behaves for both kinds of users.

### Type checks

Running type checks with mypy:

    uv run mypy french_test_app

### Test coverage

To run the tests, check your test coverage, and generate an HTML coverage report:

    uv run coverage run -m pytest
    uv run coverage html
    uv run open htmlcov/index.html

#### Running tests with pytest

    uv run pytest

### Live reloading and Sass CSS compilation

Moved to [Live reloading and SASS compilation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally.html#using-webpack-or-gulp).

## Deployment

The following details how to deploy this application.

### Docker

See detailed [cookiecutter-django Docker documentation](https://cookiecutter-django.readthedocs.io/en/latest/3-deployment/deployment-with-docker.html).

### Production checklist (Fly or any server)

- Use PostgreSQL (`DATABASE_URL`) in production.
- Release command runs migrations only:

      python manage.py migrate --noinput

- Do not run `load_questions` on each deploy.
- Set `MOCK_SSO=False` in production.

### Local mock SSO mode (no real Microsoft login)

For local testing with teacher/student accounts without Azure setup:

    export MOCK_SSO=True

Then use normal local accounts (admin + users in `Enseignants` group) to test
all role flows. The Microsoft button is hidden in this mode.

### Keep professor corrections safe

Once professors edit questions/answers in production, the database is source of truth.

Before deploy, save a local backup:

    fly ssh console -C "python manage.py dump_catalogue -" > backups/catalogue-$(date +%F).json

Optional full DB backup:

    fly postgres backup

Deploy:

    fly deploy

If needed, restore from local file:

    fly ssh console -C "python manage.py load_catalogue -" < backups/catalogue-YYYY-MM-DD.json

### One-time initial data load

Use this only once on a fresh database:

    uv run python manage.py seed_catalogue

If records already exist, command exits with an error unless `--force` is passed.
