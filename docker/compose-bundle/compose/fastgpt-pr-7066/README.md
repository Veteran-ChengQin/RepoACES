# fastgpt-pr-7066 Docker Compose evaluator

## Build image

``powershell
docker compose build
``

## Run env check

``powershell
docker compose run --rm evaluator
``

## Run a phase

Edit .env and set MODE=test, MODE=build, MODE=docker, or MODE=all, then run:

``powershell
docker compose run --rm evaluator
``

## Run with a patch

Copy the candidate patch to this folder as candidate.patch, then run:

``powershell
docker compose -f docker-compose.yml -f docker-compose.patch.yml run --rm evaluator
``

Results are written to:

``text
../../dist/compose-results/fastgpt-pr-7066/
``

Image ref:

``text
repoaces/eval-7066:445a5dc45465
``
