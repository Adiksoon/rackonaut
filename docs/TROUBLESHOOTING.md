# Troubleshooting

| Symptom | First check |
|---|---|
| GitHub reports repository not found | Confirm your Git client uses the account Adrian invited and that you accepted the invitation. |
| ROS tools or packages resolve from an earlier project | Open a fresh Bash shell and run the Rackonaut activation script. Run `scripts/robotics/check`, then inspect `AMENT_PREFIX_PATH` and `which python3`. Build from the Rackonaut clone. |
| `gz` points to Classic | On Jammy with both generations installed, Fortress uses `ign gazebo`. Use the Rackonaut launcher and check the active world against the contract. |
| World opens with missing models | Check the simulator's first unresolved URI, the resource paths set by the project script, and the declared source and version of the missing model. |
| Simulator runs but camera data is absent | Verify that simulation time advances, then check the simulator camera topic, bridge mapping, ROS frame and QoS. Start with the default software renderer on the integration host. Capture the first EGL or OGRE2 error if the headless run fails. Stop the reference process before another smoke test. |
| OpenCV or cv_bridge import fails | Check the interpreter and package locations reported by the robotics check. Keep robotics Python separate from the backend virtual environment and user-site ML packages. |
| ROS nodes do not see each other | Check that both shells use the project domain and RMW. Inspect endpoints with `ros2 topic info --verbose` from the project environment. Check for two publishers when switching from mock to simulator. |
| Mock API fails to bind or dashboard cannot reach it | Check the port, health route, frontend origin, and browser diagnostics. Stop the previous API instance using Ctrl+C in its own terminal. A different API port also requires updating the client. |
| API responds with a validation or conflict error | Inspect the response and match the request to the OpenAPI schema. Check the inspection, slot, observation ID, and whether the payload reuses an existing ID with different content. |

Report your OS, Git commit, role, exact command, and first relevant error. Remove account credentials and private data from any shared logs. [Baseline evidence](TEST_RESULTS.md)
