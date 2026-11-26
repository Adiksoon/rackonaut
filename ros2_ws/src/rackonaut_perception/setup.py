from setuptools import setup

package = "rackonaut_perception"

setup(
    name=package,
    version="0.1.0",
    packages=[package],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package}"]),
        (f"share/{package}", ["package.xml"]),
        (f"share/{package}/config", ["config/markers.json"]),
    ],
    install_requires=["setuptools"],
    maintainer="Rackonaut team",
    maintainer_email="rackonaut@example.invalid",
    description="Live warehouse inspection from the ROS camera.",
    license="Proprietary",
    entry_points={"console_scripts": [
        "inspect = rackonaut_perception.node:main",
        "inspect_frame = rackonaut_perception.frame:main",
    ]},
)
