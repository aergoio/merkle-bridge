import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="merkle-bridge",
    version="0.0.2",
    author="Pierre-Alain Ouvrard",
    author_email="pierrealain@blocko.io",
    description="POC implementation of the merkle-bridge",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/aergoio/merkle-bridge",
    packages=setuptools.find_packages(),
    install_requires=[],
    classifiers=[
                "Programming Language :: Python :: 3.7",
                "License :: OSI Approved :: MIT License",
                "Operating System :: OS Independent",
            ],
)
