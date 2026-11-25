from setuptools import setup

package = "rackonaut_control"

setup(
    name=package,
    version="0.1.0",
    packages=[package],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package}"]),
        (f"share/{package}", ["package.xml"]),
        (f"share/{package}/launch", ["launch/control.launch.py"]),
        (f"share/{package}/web", ["web/index.html", "web/app.js", "web/style.css",
                                  "web/twin.js", "web/twin-scene.js", "web/twin.css"]),
        (f"share/{package}/web/vendor", ["web/vendor/three.module.min.js", "web/vendor/three.core.min.js",
                                        "web/vendor/OrbitControls.js", "web/vendor/three-LICENSE.txt"]),
    ],
    install_requires=["setuptools"],
    maintainer="Rackonaut team",
    maintainer_email="rackonaut@example.invalid",
    description="Local web mission control for the Rackonaut simulator.",
    license="Proprietary",
    entry_points={"console_scripts": ["serve = rackonaut_control.node:main"]},
)
