import setuptools

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = f.read().splitlines()

setuptools.setup(
    name="thonny-edulint",
    version="0.5.1",
    author="Anna Rechtackova",
    author_email="anna.rechtackova@mail.muni.cz",
    description="A plugin that adds EduLint warnings to the Thonny Python IDE.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=["thonnycontrib.edulint"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Environment :: Plugins",
        "Intended Audience :: Education",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    url="https://github.com/GiraffeReversed/thonny-edulint",
    project_urls={
        "Bug Tracker": "https://github.com/GiraffeReversed/thonny-edulint/issues",
    },
    install_requires=requirements,
    python_requires=">=3.7",
    package_data={"thonnycontrib.edulint": ["broom-green.png"]},
)
