# RepoACES PR Docker Compose Bundle

This bundle contains:

- configs/*.eval.json
- compose/fastgpt-pr-*/docker-compose.yml
- dockerfiles/FastGPT.Evaluator.Dockerfile
- runtime evaluator scripts
- PowerShell helper scripts

Quick start:

1. Open PowerShell in this bundle root.
2. Pick a PR, for example:

   cd .\compose\fastgpt-pr-7138

3. Build:

   docker compose build

4. Run env check:

   docker compose run --rm evaluator

5. Run with patch:

   copy D:\path\to\candidate.patch .\candidate.patch
   docker compose -f docker-compose.yml -f docker-compose.patch.yml run --rm evaluator

Change MODE in .env to test/build/docker/all when needed.
