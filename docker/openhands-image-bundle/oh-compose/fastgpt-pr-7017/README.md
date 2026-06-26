# fastgpt-pr-7017 OpenHands workspace image

This image prepares a FastGPT base-commit workspace for common root-level build and test feedback.

Build:

``powershell
docker compose build
``

Open a shell for manual verification:

``powershell
docker compose run --rm --entrypoint bash openhands
``

Common command helper inside the container:

``bash
bash /opt/repoaces-oh/openhands-common-commands.sh env
bash /opt/repoaces-oh/openhands-common-commands.sh build
bash /opt/repoaces-oh/openhands-common-commands.sh test
bash /opt/repoaces-oh/openhands-common-commands.sh compose
``
