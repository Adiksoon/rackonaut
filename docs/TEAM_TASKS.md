# Team tasks

The authoring slots below can be created on the owning branch as work begins. Record major state changes here or in the linked pull request.

| Owner | Scope | Branch | Authoring slot | Initial state |
|---|---|---|---|---|
| Adrian | Warehouse world, then computer vision, and overall integration | `feature/warehouse`, `feature/perception` | `ros2_ws/src/rackonaut_warehouse/`, `ros2_ws/src/rackonaut_perception/` | Reference materials available. Team implementation and acceptance pending. |
| Michał | Drone selection, camera, teleoperation, and ROS transport | `feature/drone` | `ros2_ws/src/rackonaut_drone/` | Confirm simulator and report smoke result before adopting a drone model. |
| Vahid, proposed | Inventory comparison and REST API over mock SAP data | `feature/backend` | `backend/` | Fixture API and contracts available for independent work. Confirm assignment. |
| Tharindu, proposed | Dashboard for inspection status and discrepancies | `feature/dashboard` | `dashboard/` | REST examples and a local fixture API available. Confirm assignment and framework. |

Adrian coordinates `contracts/`, reference packages, and integration configuration. Confirm interface changes with Adrian and the owners on both sides. Team onboarding is complete for an individual only when they report the checklist in their role guide.

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
