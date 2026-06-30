# fastgpt-pr-6162 OpenHands workspace image

This image is a pre-exploration FastGPT workspace. It prepares the base commit and gives OpenHands repository-wide commands first.

Build:

```powershell
docker compose build
```

Open a shell for manual verification:

```powershell
docker compose run --rm --entrypoint bash openhands
```

Common command helper inside the container:

```bash
bash /opt/repoaces-oh/openhands-common-commands.sh env
bash /opt/repoaces-oh/openhands-common-commands.sh build
bash /opt/repoaces-oh/openhands-common-commands.sh test
bash /opt/repoaces-oh/openhands-common-commands.sh compose
```
