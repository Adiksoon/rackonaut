from glob import glob
from setuptools import setup

package = "rackonaut_showcase"

setup(
    name=package,
    version="0.1.0",
    packages=[package],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package}"]),
        (f"share/{package}", ["package.xml"]),
        (f"share/{package}/config", glob("config/*")),
        (f"share/{package}/launch", glob("launch/*.launch.py")),
    ],
    entry_points={"console_scripts": ["observe = rackonaut_showcase.observe:main"]},
)
