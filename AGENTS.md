# Rackonaut agent instructions

Rackonaut is a RobotHack 2026 warehouse inspection prototype. The first project milestone is teleoperation with a working camera inside the simulated warehouse.

## Read before editing

1. [README](README.md)
2. [Architecture](docs/ARCHITECTURE.md)
3. [Interface index](docs/INTERFACES.md) and its linked contracts
4. [Team task register](docs/TEAM_TASKS.md)
5. The onboarding guide for your [role](README.md#start-here)

Work on the assigned module and branch. Check `git status -sb` and existing diffs before editing. Preserve changes outside your task and coordinate overlapping paths with the module owner.

## Shared baseline

- Robotics uses Ubuntu 22.04 or WSL2 Ubuntu 22.04, ROS 2 Humble, system Python 3.10, and provisionally Gazebo Fortress. Use the project activation script for the underlay, ROS domain, and simulator resource paths.
- Backend uses an isolated Python environment. See the backend guide for supported Windows and Linux interpreters. Dashboard development uses the local REST mock and can choose its framework independently.
- The canonical contracts live in `contracts/`. Authoring slots and owners are in the task register. Reference packages and fixture inputs serve as integration test resources.
- Agree changes to the ROS/Gazebo versions, topics, types, frames, schemas, shared configuration, or repository layout with Adrian and the owners of affected modules before editing them. Keep an agreed decision and update affected contracts, fixtures, and tests together.
- Preserve other users' work. Keep secrets, machine paths, unlicensed assets, environments, and build output out of Git. Avoid global environment edits and large dependencies unless explicitly agreed.
- Follow the [Git workflow](docs/TEAM_TASKS.md#git-workflow). Keep `main` usable, send focused pull requests, and preserve published branch history.

## Verification and handoff

Run the setup and smoke check for your role. Then run the smallest test for the module change and any shared contract check it affects. Record the commit, operating system, versions, command, result, and a short relevant excerpt for a failure. Label fixture, reference simulation, and integration results accurately. Use [test results](docs/TEST_RESULTS.md) for baseline evidence and report module results in the pull request.

For a compatibility issue, include the failing command and its first relevant error, the affected contract, what has already worked, and the smallest change or decision needed. Do not change teammates' modules to work around a local setup issue.
