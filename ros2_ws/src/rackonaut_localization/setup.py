from setuptools import setup

package = "rackonaut_localization"
setup(
    name=package,
    version="0.1.0",
    packages=[package],
    data_files=[("share/ament_index/resource_index/packages", ["resource/" + package]),
                ("share/" + package, ["package.xml"])],
    license="Proprietary",
    maintainer="Rackonaut team",
    maintainer_email="rackonaut@example.invalid",
    description="Sensor-based localization and accumulated LiDAR mapping.",
    entry_points={"console_scripts": [
        "localize = rackonaut_localization.node:main",
        "validate_pose = rackonaut_localization.validation:main",
    ]},
)
