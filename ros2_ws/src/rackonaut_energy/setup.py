from setuptools import setup

setup(
    name="rackonaut_energy",
    version="0.1.0",
    packages=["rackonaut_energy"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/rackonaut_energy"]),
        ("share/rackonaut_energy", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    maintainer="Rackonaut team",
    maintainer_email="rackonaut@example.invalid",
    description="Odometry-derived battery and dock simulation.",
    license="Proprietary",
    entry_points={"console_scripts": ["manage = rackonaut_energy.node:main"]},
)
