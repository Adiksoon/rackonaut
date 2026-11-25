from setuptools import setup

package = "rackonaut_mission"

setup(
    name=package,
    version="0.1.0",
    packages=[package],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package}"]),
        (f"share/{package}", ["package.xml"]),
        (f"share/{package}/config", ["config/showcase.json", "config/showcase.rviz"]),
        (f"share/{package}/launch", ["launch/showcase.launch.py"]),
        (f"share/{package}/templates", ["templates/inspection.html"]),
    ],
    install_requires=["setuptools"],
    maintainer="Rackonaut team",
    maintainer_email="rackonaut@example.invalid",
    description="Waypoint inspection and API confirmation for the Rackonaut showcase.",
    license="Proprietary",
    entry_points={"console_scripts": [
        "run_mission = rackonaut_mission.node:main",
        "export_report = rackonaut_mission.report:main",
    ]},
)
