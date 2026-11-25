# Team tasks

The stable reference demo is pinned at [`demo-baseline`](https://github.com/Adiksoon/rackonaut/tree/demo-baseline), commit `6d10e45`. See the [integration guide](INTEGRATION.md) for the three launch variants and module acceptance checks. GitHub status was checked on 25 November 2026.

| Owner | Scope | Branch | Authoring slot | Integration status |
|---|---|---|---|---|
| Adrian | Warehouse, computer vision, mission and integration | `feature/warehouse`, `feature/perception`, `feature/mission`, `integration/demo-baseline` | `ros2_ws/src/rackonaut_warehouse/`, `ros2_ws/src/rackonaut_perception/`, `ros2_ws/src/rackonaut_mission/` | Reference drone and mock API verified in a five-stop mission. Integration branch ready for review. |
| Michał | Drone selection, camera, teleoperation and ROS transport | `feature/drone` | `ros2_ws/src/rackonaut_drone/` | **BLOCKED** on a published model and launch instructions. Deliver camera, odometry and control evidence. |
| Vahid | Inventory comparison and REST API over Mock SAP | `feature/backend` | `backend/` | **BLOCKED** on a published backend. Deliver startup instructions and results from the recorded-flight replay. |
| Tharindu | Dashboard for inspection status and discrepancies | `feature/dashboard` | `dashboard/` | **BLOCKED** on a published dashboard. Deliver startup instructions and a view bound to a selected inspection ID. |

Adrian coordinates `contracts/`, reference packages, and integration configuration. Confirm interface changes with Adrian and the owners on both sides. Team onboarding is complete for an individual only when they report the checklist in their role guide.

For each module, publish the branch and share its PR or commit, OS and versions, launch command, smoke result and current blocker. Keep the branch focused on the owner's module. Coordinate the base with Adrian before rebasing shared work.

## Git workflow

After accepting the repository invitation, clone it and start from `main`. Use the branch name from the table. The example creates the warehouse branch.

```sh
git fetch origin
git switch main
git pull --ff-only
git switch -c feature/warehouse
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
