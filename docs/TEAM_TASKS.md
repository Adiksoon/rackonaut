# Team tasks

## Verified team contributions

| Team member | Delivered work | Integration and attribution |
| --- | --- | --- |
| Adrian Zygarowski (`Adiksoon`) | Warehouse and showcase (`d9b1d3d`), live computer vision (`4d971fc`), Mock SAP and business recommendations (`3c7c97b`), operator workflows and Results (`f50cfee`), shared integration and release validation, and the multi-sortie reference calibration and warehouse library. | See the [integrated stack](FULL_SYSTEM_INTEGRATION.md), [full reference survey](FULL_WAREHOUSE_CALIBRATION.md) and [companion warehouse library](GETTING_STARTED.md#additional-warehouses). |
| Michał (`michalczaplinski5`) | Delivered the X3 drone, camera, ROS bridges and frame integration, and contributed the X3 flight, localization and energy acceptance work. | [PR #7](https://github.com/Adiksoon/rackonaut/pull/7) has seven cherry-picked commits in the common stack. [PR #9](https://github.com/Adiksoon/rackonaut/pull/9) was merged as `0953cbb` and is in the shared history. Those PRs identify Michał as submitter. The individual commits retain their recorded Git authors. |
| Vahid Abdullayev (`abzdullayezz`) | Standalone inventory import and validation tool, templates, examples, documentation and 54 regression tests. | [PR #8](https://github.com/Adiksoon/rackonaut/pull/8), authored commit `0efb6b0`, included through merge `3f42ff7`. The tool is separate from active warehouse calibration and Mock SAP. |
| Tharindu | Dashboard work was proposed during onboarding. | The audited branches and PRs gave no attributable delivery. |

Git records the X3 standalone acceptance commits `28bdaf7` and `a2fd71c` and the original Warehouse in Motion scenario `32d4092` under `Codex`. The repository evidence does not identify a human author for those three commits. See the [final branch audit](FINAL_BRANCH_AUDIT.md) for the original and adapted evidence.

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
