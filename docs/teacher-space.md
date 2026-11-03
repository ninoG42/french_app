# Espace enseignant OP001

## Tester la démonstration locale

Les réglages `config.settings.demo` utilisent exclusivement `.local-demo/demo.sqlite3`.
Les courriels sont désactivés. L’intégration IA a été retirée de l’application. Le compte enseignant de démo
peut importer des questions. Les comptes et les
résultats de démonstration sont fictifs ; le catalogue vient des exercices existants.

```sh
.venv/bin/python manage.py runserver 127.0.0.1:8011 --settings=config.settings.demo
```

Ouvrir http://127.0.0.1:8011/quiz/enseignant/ et se connecter avec le compte enseignant
fourni lors de la préparation. Le compte étudiant permet de répondre à un exercice,
puis de retrouver la nouvelle réponse dans le suivi enseignant après actualisation.
La commande `seed_demo` refuse les réglages ordinaires et ne réinitialise pas une
démonstration existante.

Pour préparer une démo sur une autre machine : créer `.local-demo`, migrer avec les
réglages demo, importer un catalogue avec `loaddata`, puis lancer `seed_demo` avec
ces mêmes réglages. Cette commande affiche les identifiants de deux comptes de test.

## Utiliser avec de vrais comptes

1. Appliquer les migrations : `.venv/bin/python manage.py migrate`.
2. Dans l’administration Django, créer un **groupe de cours**.
3. Y rattacher le compte enseignant de Florence et les comptes des étudiants.
4. Florence accède à `/quiz/enseignant/`. Aucun accès à l’administration n’est requis.

Aucun rôle n’est attribué automatiquement à partir d’une adresse e-mail. Une
enseignante ne peut lire que les groupes auxquels elle est explicitement rattachée.
Un superutilisateur peut consulter tous les groupes. Retirer une enseignante d’un
groupe retire immédiatement l’accès à ce groupe. Les comptes étudiants inactifs ne
sont pas affichés. L’importation des questions requiert les permissions Django
`quiz.add_question` et `quiz.change_question` ; être enseignant ne les confère pas.

## Indicateurs

- **Premier essai** : première tentative enregistrée par étudiant et question, dans
  l’ordre date puis identifiant. Les passages sont inclus comme non réussis. Les
  révisions répétées n’augmentent pas ce taux. Les réponses historiques sont incluses,
  même antérieures à l’affectation au groupe.
- **Classements** : questions tentées par au moins trois étudiants ; cinq résultats
  par classement. Avec peu de questions, la même peut figurer dans les deux listes.
- **Questions explorées** : questions avec au moins une tentative / catalogue total.
- **Acquise** : règle existante, au moins cinq tentatives et 80 % de réussite.
- **Activité** : toutes les tentatives des quatorze derniers jours, fuseau Europe/Zurich.
- **Sans réponse** : tiret (absence de données), distinct d’un taux de réussite de 0 %.

Les statistiques reflètent les données actuellement conservées. Une réinitialisation
de progression par l’étudiant supprime aussi ses réponses des vues enseignantes.
Aucun résultat ne constitue une note d’examen ou une décision d’évaluation.

## Mise en forme des questions

Dans **Banque de questions** (`/quiz/enseignant/questions/`), le filtre **À contrôler**
liste les questions non encore validées. L’édition propose une petite barre d’outils :

Disponible sur tous les formulaires question (banque, série, module) :

- **Énoncé, propositions (1–4, A, T), explication et texte de référence** :
  éditeur visuel (gras / italique / guillemets `« … »`) — l’enseignante voit le
  style, pas les balises. Une sélection est entourée (`mot` → `« mot »`) ;
  recliquer sur **« »** retire les guillemets. À l’enregistrement, HTML limité
  (`b`, `i`, `em`, `strong`, `br`) ; le reste est neutralisé. Affiché aussi côté
  étudiant.

Les guillemets peuvent aussi être collés directement depuis le clavier.

## Design et validation

Palette inspirée du site public HEP Vaud : bleu, bleu clair, jaune. Marque propre
OP001 et mention « Projet pilote », sans reproduire le logo institutionnel.
Les pages de connexion, exercices, ressources et progression partagent ce thème.

Tests ciblés :

```sh
.venv/bin/python -m pytest french_test_app/quiz/tests/test_teacher.py -q
```

La suite générale contient deux blocages préexistants : un fichier de test OpenAPI
incomplet et un test Celery alors que Celery n’est pas installé. Les tests navigateur
historiques nécessitent un environnement Playwright distinct. Les parcours principaux
ont été vérifiés dans le navigateur de développement.

Le raccordement Keycloak, l’hébergement Infomaniak et l’envoi de vraies invitations
ne sont pas inclus dans cette évolution locale.
