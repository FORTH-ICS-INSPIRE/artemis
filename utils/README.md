ARTEMIS is an open-source tool, that implements a defense approach against BGP prefix hijacking attacks.

This package holds all the utility functions that are shared between the different modules.

Read more at [bgpartemis.org](http://bgpartemis.org/) and the [docs](https://bgpartemis.readthedocs.io/en/latest/).

Instructions on publishing a package update:

```
# follow instructions to build a correct $HOME/.pypirc for artemis-utils
https://docs.gitlab.com/ee/user/packages/pypi_repository/
# generate pypi token
https://pypi.org/manage/account/token/
# update the package (code, version, files, etc.)
python3 setup.py sdist bdist_wheel
twine upload dist/*
```
