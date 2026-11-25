from setuptools import setup

package = "rackonaut_avoidance"

setup(
    name=package,
    version="0.1.0",
    packages=[package],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package}"]),
        (f"share/{package}", ["package.xml"]),
    ],
    maintainer="Rackonaut team",
    maintainer_email="rackonaut@example.invalid",
    description="Sensor-based clearance and local 3D navigation.",
    license="Proprietary",
)
