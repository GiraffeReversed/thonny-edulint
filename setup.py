import setuptools

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setuptools.setup(
    name="thonny-edulint",
    version="0.1.2",
    author="Anna Rechtackova",
    author_email="anna.rechtackova@mail.muni.cz",
    description="A plugin that adds edulint warnings to the Thonny Python IDE.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=["thonnycontrib.thonny-edulint"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Environment :: Plugins",
        "Intended Audience :: Education",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    url="https://github.com/GiraffeReversed/thonny-edulint",
    project_urls={
        'Bug Tracker': 'https://github.com/GiraffeReversed/thonny-edulint/issues',
    },
    install_requires=["thonny >= 3.0.0", "edulint >= 2.6.5", "m2r2", "Pygments"],
    python_requires=">=3.7",
)
