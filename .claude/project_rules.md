This workspace and server are fully trusted.

Claude is allowed to execute all development commands without asking permission.

Allowed tools include:
bash, curl, git, python, node, npm, grep, sed, awk, docker, docker compose.

Do not prompt for confirmation for normal development tasks such as:
- running scripts
- checking logs
- reading or editing files
- running docker containers
- testing APIs
- running builds or tests

Only ask for confirmation if an action is destructive, such as:
- deleting system directories
- wiping databases
- permanently removing docker volumes
- modifying system configuration outside this project

All other actions should be treated as pre-approved.
