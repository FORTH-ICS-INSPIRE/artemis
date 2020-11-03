ARTEMIS is an open-source tool, that implements a defense approach against BGP prefix hijacking attacks.

This package holds all the utility functions that are shared between the different modules.

Read more at [bgpartemis.org](http://bgpartemis.org/) and the [docs](https://bgpartemis.readthedocs.io/en/latest/).

Instructions on publishing a package update:

```
# update the package (code, version, files, etc.)
python3 setup.py sdist bdist_wheel
python3 -m twine upload dist/*
```
