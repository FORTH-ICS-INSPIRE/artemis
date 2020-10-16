from os import path

import setuptools

this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setuptools.setup(
    name="artemis_utils",
    version="1.0.1",
    author="Dimitrios Mavrommatis",
    author_email="jim.mavrommatis@gmail.com",
    description="ARTEMIS utility modules",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/FORTH-ICS-INSPIRE/artemis",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=[
        "kombu==4.6.7",
        "ruamel.yaml==0.16.5",
        "ujson==1.35",
        "PyYAML==5.3",
        "gql==0.4.0",
        "ipaddress==1.0.23",
        "psycopg2==2.8.4",
    ],
)
