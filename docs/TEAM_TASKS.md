# Team tasks

## Current responsibilities

| Owner | Scope | Integration status |
| --- | --- | --- |
| Adrian | Integrated demonstrator, warehouse, computer vision, autonomy, Mock SAP backend and business recommendations | Owns the current simulation, Control Center, Engineering Showcase and their release checks. |
| Michał | Independent drone, camera and ROS transport work | Review after delivery of an identifiable model revision, license, launch instructions, interface samples and an isolated test result. The integrated demo uses the reference drone. |

Earlier planning proposed a separate backend role for Vahid and a dashboard role for Tharindu. The repository contains the fixture API, dashboard onboarding and contracts for independent work. GOAL 17 delivered the integrated backend under Adrian's responsibility. Integration credit for separate work follows the supplied artifacts and Git history. This register records technical responsibility and leaves team membership to the team.

Adrian coordinates shared interfaces in `contracts/`. Confirm interface updates with the affected owners. Use the [onboarding guides](../README.md#team-onboarding), [integration gates](INTEGRATION.md) and each role's readiness checklist.

## Git workflow

After accepting the repository invitation, clone it and start from `main`. Create a task branch for your assignment. The example uses a warehouse topic branch.

```sh
git fetch origin
git switch main
git pull --ff-only
git switch -c feature/warehouse-update
```

If a branch already exists on GitHub and you own it, track it with `git switch --track origin/feature/warehouse` instead of creating another branch with the same name.

Make and test a focused change. Stage the paths you own, check the staged diff, then commit and push.

```sh
git add ros2_ws/src/rackonaut_warehouse/
git diff --cached
git commit -m "Add warehouse world package"
git push -u origin feature/warehouse
```

Open a GitHub pull request to `main` with the scope, changed contracts, setup details, test command, and result. Tag Adrian for integration review. Update a feature branch using `git fetch origin` and `git merge origin/main`. If there is a conflict, use `git status` to locate it, coordinate with the owner of the affected area, resolve the files, stage them, run the checks, and finish the merge commit. Keep the branch history and use a regular push. Merge reviewed changes into `main` in dependency order and repeat the affected smoke check.
